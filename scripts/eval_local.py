"""Local eval harness: ask the agent every golden question, score with the *same* metric code.

    uv run eval-local --label v3-baseline             # hosted agent (whatever version the endpoint serves)
    uv run eval-local --local --port 8088 --label ollama
    uv run eval-local --rows 2 --label smoke           # first two rows only

Per row it records the raw code metrics from ``src/agent`` (clash count, preference violations,
break coverage, unknown ids) *and* the 0–1 scores of the generated Foundry evaluators
(``evals/evaluators/*.py``, exec-ed like the sandbox does), so a local run and a portal run can be
compared number for number. Results go to ``evals/results/<label>.json``; render them with
``uv run eval-chart``.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from agent.contract import extract_agenda, resolve_items
from agent.metrics import Preferences, evaluate_agenda
from agent.program import load_program
from scripts.azdenv import load_env
from scripts.build_evaluators import CODE_EVALUATORS, OUT_DIR

ROOT = Path(__file__).resolve().parents[1]
GOLDEN = ROOT / "evals" / "golden.jsonl"
RESULTS = ROOT / "evals" / "results"


def load_golden(path: Path = GOLDEN, rows: int | None = None) -> list[dict[str, Any]]:
    items = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    return items[:rows] if rows else items


def load_grader(code: str, module_name: str) -> Any:
    """exec one evaluator's code_text as its own module (the way the sandbox does) and return grade()."""
    import sys
    import types

    module = types.ModuleType(module_name)
    sys.modules[module_name] = module  # dataclasses resolve the defining module through sys.modules
    exec(compile(code, module_name, "exec"), module.__dict__)
    return module.__dict__["grade"]


def load_graders(directory: Path = OUT_DIR) -> dict[str, Any]:
    """grade() of every generated evaluator under evals/evaluators/."""
    return {
        name: load_grader((directory / f"{name}.py").read_text(encoding="utf-8"), f"ntk_evaluator_{name}")
        for name in CODE_EVALUATORS
    }


def score_row(row: dict[str, Any], answer: str, graders: dict[str, Any]) -> dict[str, Any]:
    """Raw metrics (repo code) + evaluator scores (generated code) for one answer."""
    program = load_program()
    agenda = extract_agenda(answer)
    raw: dict[str, Any]
    if agenda is None:
        raw = {
            "parsed": False,
            "items": 0,
            "clash_count": None,
            "violations": None,
            "break_ok": None,
            "unknown_ids": [],
        }
    else:
        resolved = resolve_items(agenda, program.get)
        prefs = Preferences.from_persona(
            {
                "earliest_start": row.get("earliest_start") or None,
                "latest_end": row.get("latest_end") or None,
                "min_break_minutes": row.get("min_break_minutes") or None,
            }
        )
        report = evaluate_agenda(resolved["items"], prefs, day=row.get("day") or agenda.get("day"))
        pv = report["preference_violations"]
        raw = {
            "parsed": True,
            "items": report["items"],
            "clash_count": report["clash_count"],
            "violations": len(pv["before_earliest"]) + len(pv["off_day"]) + len(pv["after_latest"]),
            "before_earliest": pv["before_earliest"],
            "after_latest": pv["after_latest"],  # the guard's whole reason to exist: record it
            "off_day": pv["off_day"],
            "break_ok": report["break_coverage"]["ok"],
            "longest_gap_minutes": report["break_coverage"]["longest_gap_minutes"],
            "unknown_ids": resolved["unknown_ids"],
        }
    item = {**row, "sample": {"output_text": answer}}
    scores = {name: grade({}, item) for name, grade in graders.items()}
    return {"raw": raw, "scores": scores}


def summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Quality rates over the rows the agent actually answered.

    A row that came back throttled or errored says nothing about agenda quality, so it is counted
    in ``failed`` and kept out of the rates — otherwise a rate-limited run would look like a
    quality regression on the chart.
    """
    scored = [r for r in rows if r.get("raw")]
    answered = [r for r in scored if not r.get("error") and (r.get("answer") or "").strip()]
    parsed = [r for r in answered if r["raw"]["parsed"]]
    n = len(answered)

    def rate(pred) -> float:
        return round(sum(1 for r in answered if pred(r)) / n, 3) if n else 0.0

    return {
        "rows": len(scored),
        "answered": n,
        "failed": len(scored) - n,
        "parsed": len(parsed),
        "total_clashes": sum(r["raw"]["clash_count"] or 0 for r in parsed),
        "rows_with_clashes": sum(1 for r in parsed if r["raw"]["clash_count"]),
        "clash_free_rate": rate(lambda r: r["raw"]["parsed"] and r["raw"]["clash_count"] == 0),
        "preferences_ok_rate": rate(lambda r: r["raw"]["parsed"] and r["raw"]["violations"] == 0),
        "break_ok_rate": rate(lambda r: r["raw"]["parsed"] and bool(r["raw"]["break_ok"])),
        "unknown_id_rows": sum(1 for r in parsed if r["raw"]["unknown_ids"]),
        "mean_scores": {
            name: round(sum(r["scores"][name] for r in answered) / n, 3) if n else 0.0
            for name in CODE_EVALUATORS
        },
        "mean_seconds": round(sum(r.get("seconds", 0) for r in answered) / n, 1) if n else 0.0,
    }


def _ask(
    client, question: str, *, attempts: int = 3, pause: float = 15.0
) -> tuple[str, str | None, list[str], float, str | None]:
    """One question, retried on an empty answer.

    Over the deployment's tokens-per-minute limit the hosted agent answers **HTTP 200 with
    ``status: "failed"``, an empty ``output_text`` and the real reason in ``response.error``**
    ("Model deployment rate limit exceeded…"); the OpenAI SDK raises nothing, so a naive caller
    just sees an empty string. Verified 2026-09-06 (the talk's write-up, D-22). Hence: retry, and report
    ``response.error`` rather than inventing an explanation.

    The deployment now runs at capacity 200 (200,000 TPM / 200 RPM, D-22b), so this path should
    stay cold — keep it anyway: it is the only thing that tells a throttled row apart from a
    genuinely bad answer, and capacity is a deployment setting anyone can lower again.
    """
    started = time.monotonic()
    text, response_id, calls, failure = "", None, [], None
    for attempt in range(1, attempts + 1):
        response = client.responses.create(input=question)
        response_id = response.id
        calls = [item.name for item in response.output if getattr(item, "type", "") == "function_call"]
        text = response.output_text
        error = getattr(response, "error", None)
        failure = getattr(error, "message", None) or (str(error) if error else None)
        if text.strip() or attempt == attempts:
            break
        print(
            f"  {failure or 'empty answer'} — retrying in {pause:.0f}s ({attempt}/{attempts - 1})",
            file=sys.stderr,
        )
        time.sleep(pause)
    return text, response_id, calls, time.monotonic() - started, failure


def run(args: argparse.Namespace) -> dict[str, Any]:
    from scripts.invoke import _cloud_client, _local_client

    client, base_url = _local_client(args.port) if args.local else _cloud_client(args.agent)
    golden = load_golden(rows=args.rows)
    graders = load_graders()
    print(f"→ {base_url}  ·  {len(golden)} rows  ·  concurrency {args.concurrency}", file=sys.stderr)

    def one(row: dict[str, Any]) -> dict[str, Any]:
        if args.delay and not args.local:
            time.sleep(args.delay)  # stay under the deployment's tokens-per-minute limit
        try:
            answer, response_id, calls, seconds, error = _ask(client, row["query"])
        except Exception as exc:  # keep going; the row scores 0
            answer, response_id, calls, seconds, error = "", None, [], 0.0, f"{type(exc).__name__}: {exc}"
        result = score_row(row, answer, graders)
        return {
            "id": row.get("id"),
            "query": row["query"],
            "answer": answer,
            "response_id": response_id,
            "tools": calls,
            "seconds": round(seconds, 1),
            "error": error,
            **result,
        }

    with ThreadPoolExecutor(max_workers=args.concurrency) as pool:
        rows = list(pool.map(one, golden))
    return {
        "label": args.label,
        "target": base_url,
        "timestamp": datetime.now(UTC).isoformat(timespec="seconds"),
        "summary": summarize(rows),
        "rows": rows,
    }


def format_table(result: dict[str, Any]) -> str:
    header = f"{'id':<4} {'clash':>5} {'viol':>4} {'break':>5} {'unk':>3} {'s':>5}"
    lines = [f"{header}  scores(clash/pref/break)  tools"]
    for r in result["rows"]:
        raw = r["raw"]
        if not raw["parsed"]:
            blank = f"{'-':>5} {'-':>4} {'-':>5} {'-':>3}"
            lines.append(f"{r['id']:<4} {blank} {r.get('seconds', 0):>5}  no agenda  {r.get('error') or ''}")
            continue
        s = r["scores"]
        lines.append(
            f"{r['id']:<4} {raw['clash_count']:>5} {raw['violations']:>4} {str(raw['break_ok']):>5} "
            f"{len(raw['unknown_ids']):>3} {r['seconds']:>5}  "
            f"{s['ntk_clash_free']:.2f}/{s['ntk_preferences']:.2f}/{s['ntk_break_coverage']:.2f}      "
            f"{','.join(r.get('tools') or []) or '-'}"
        )
    sm = result["summary"]
    lines.append(
        f"— {sm.get('answered', sm['rows'])}/{sm['rows']} answered "
        f"({sm.get('failed', 0)} throttled or errored) · "
        f"clashes {sm['total_clashes']} in {sm['rows_with_clashes']} rows · "
        f"clash-free {sm['clash_free_rate']:.0%} · prefs ok {sm['preferences_ok_rate']:.0%} · "
        f"break ok {sm['break_ok_rate']:.0%} · mean {sm['mean_seconds']} s"
    )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    load_env(ROOT)
    parser = argparse.ArgumentParser(description="Run the golden set against the agent and score it locally")
    parser.add_argument("--label", default="run", help="result label (file name under evals/results/)")
    parser.add_argument("--rows", type=int, default=None, help="only the first N golden rows")
    parser.add_argument("--local", action="store_true", help="target the local host instead of Foundry")
    parser.add_argument("--port", type=int, default=int(os.environ.get("PORT", "8088")))
    parser.add_argument("--agent", default=os.environ.get("AGENT_NAME", "ntk-asistent"))
    parser.add_argument(
        "--concurrency", type=int, default=4, help="parallel calls (fine at capacity 200; see _ask)"
    )
    parser.add_argument(
        "--delay", type=float, default=0.0, help="seconds to wait before each cloud call (TPM pacing)"
    )
    parser.add_argument("--out", default=None, help="result file (default evals/results/<label>.json)")
    args = parser.parse_args(argv)

    result = run(args)
    out = Path(args.out) if args.out else RESULTS / f"{args.label}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(format_table(result))
    print(f"wrote {out.relative_to(ROOT) if out.is_relative_to(ROOT) else out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
