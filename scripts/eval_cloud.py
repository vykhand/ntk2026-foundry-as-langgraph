"""The platform eval run (Act 3): the hosted agent as the target, our registered evaluators as judges.

    uv run eval-cloud --version 3                # code-based metrics only (the live set, ~2 min)
    uv run eval-cloud --version 3 --full         # + the two LLM judges (cached run)
    uv run eval-cloud --version 4 --label v4-improved

Why not `azd ai agent eval run`: azd references custom evaluators bare, and Foundry rejects code-based
evaluators without ``pass_threshold`` and a data mapping (the talk's write-up, D-20). This script does what the
Learn "evaluate an agent target" page describes, with the OpenAI evals API on the project client, and
prints the portal report URL. The per-item scores are also written to ``evals/results/cloud-<label>.json``
so ``uv run eval-chart`` can plot them next to the local harness.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from scripts.azdenv import load_env
from scripts.build_evaluators import CODE_EVALUATORS, PROMPT_EVALUATORS, data_mapping
from scripts.eval_local import RESULTS, load_golden

ROOT = Path(__file__).resolve().parents[1]
PASS_THRESHOLD = 1.0  # the code metrics are 1.0 only when the property holds
JUDGE_THRESHOLD = 4  # ordinal 1–5


def registered_versions() -> dict[str, str]:
    """Name → version written by `uv run build-evaluators --register` (pin runs to what was built)."""
    path = ROOT / "evals" / "registered.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def testing_criteria(
    *, deployment: str, full: bool, versions: dict[str, str] | None = None
) -> list[dict[str, Any]]:
    """testing_criteria entries for the registered evaluators (name = registered name)."""
    versions = registered_versions() if versions is None else versions

    def entry(name: str, init: dict[str, Any], mapping: dict[str, str]) -> dict[str, Any]:
        criterion: dict[str, Any] = {
            "type": "azure_ai_evaluator",
            "name": name,
            "evaluator_name": name,
            "initialization_parameters": init,
            "data_mapping": mapping,
        }
        if versions.get(name):
            criterion["evaluator_version"] = str(versions[name])
        return criterion

    criteria = [
        entry(name, {"deployment_name": deployment, "pass_threshold": PASS_THRESHOLD}, data_mapping())
        for name in CODE_EVALUATORS
    ]
    if full:
        criteria += [
            entry(
                name,
                {"deployment_name": deployment, "threshold": JUDGE_THRESHOLD},
                {"query": "{{item.query}}", "response": "{{sample.output_text}}"},
            )
            for name in PROMPT_EVALUATORS
        ]
    return criteria


def item_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "id": {"type": "string"},
            "query": {"type": "string"},
            "attendee": {"type": "string"},
            "day": {"type": "string"},
            "earliest_start": {"type": "string"},
            "latest_end": {"type": "string"},
            # the service validates the JSONL against this schema and stringifies scalars on the
            # way in ("'30' is not of type 'number'"), so numbers are declared as strings here;
            # the graders cast defensively
            "min_break_minutes": {"type": "string"},
            "tracks": {"type": "string"},
            "note": {"type": "string"},
            # a copy of the whole row: code-based evaluators need an `item` mapping and the service
            # only accepts {{item.<field>}}, so the graders get {{item.row}} (the talk's write-up, D-20)
            "row": {"type": "object"},
        },
        "required": ["query"],
    }


def data_source(rows: list[dict[str, Any]], *, agent: str, version: str | None) -> dict[str, Any]:
    target: dict[str, Any] = {"type": "azure_ai_agent", "name": agent}
    if version:
        target["version"] = str(version)
    return {
        "type": "azure_ai_target_completions",
        "source": {"type": "file_content", "content": [{"item": {**row, "row": dict(row)}} for row in rows]},
        "input_messages": {
            "type": "template",
            "template": [
                {
                    "type": "message",
                    "role": "user",
                    "content": {"type": "input_text", "text": "{{item.query}}"},
                }
            ],
        },
        "target": target,
    }


def summarize_items(items: list[Any]) -> dict[str, Any]:
    """Per-evaluator pass counts and mean scores from the run's output items."""
    per: dict[str, dict[str, float]] = {}
    for it in items:
        for r in getattr(it, "results", None) or []:
            get = r.get if isinstance(r, dict) else (lambda key, _r=r: getattr(_r, key, None))
            name = str(get("name") or "?")
            score = get("score")
            passed = get("passed")
            bucket = per.setdefault(name, {"n": 0, "passed": 0, "score_sum": 0.0})
            bucket["n"] += 1
            bucket["passed"] += 1 if passed else 0
            bucket["score_sum"] += float(score or 0)
    return {
        name: {
            "n": int(b["n"]),
            "passed": int(b["passed"]),
            "pass_rate": round(b["passed"] / b["n"], 3) if b["n"] else 0.0,
            "mean_score": round(b["score_sum"] / b["n"], 3) if b["n"] else 0.0,
        }
        for name, b in per.items()
    }


def main(argv: list[str] | None = None) -> int:
    load_env(ROOT)
    parser = argparse.ArgumentParser(description="Run the platform evaluation against the hosted agent")
    parser.add_argument("--version", default=None, help="agent version to evaluate (default: the endpoint's)")
    parser.add_argument("--full", action="store_true", help="add the two LLM judges")
    parser.add_argument("--rows", type=int, default=None, help="only the first N golden rows")
    parser.add_argument("--label", default=None, help="result label (default v<version>[-full])")
    parser.add_argument("--agent", default=os.environ.get("AGENT_NAME", "ntk-asistent"))
    parser.add_argument(
        "--deployment", default=os.environ.get("AZURE_AI_MODEL_DEPLOYMENT_NAME", "gpt-5.4-mini")
    )
    parser.add_argument("--no-wait", action="store_true")
    args = parser.parse_args(argv)

    from azure.ai.projects import AIProjectClient
    from azure.identity import DefaultAzureCredential

    endpoint = os.environ.get("FOUNDRY_PROJECT_ENDPOINT", "").rstrip("/")
    if not endpoint:
        sys.exit("FOUNDRY_PROJECT_ENDPOINT is not set (azd env get-values, or .env)")
    label = args.label or f"v{args.version or 'latest'}{'-full' if args.full else ''}"
    rows = load_golden(rows=args.rows)
    project = AIProjectClient(endpoint=endpoint, credential=DefaultAzureCredential())
    client = project.get_openai_client()

    eval_object = client.evals.create(
        name=f"ntk-{label}",
        data_source_config={"type": "custom", "item_schema": item_schema(), "include_sample_schema": True},
        testing_criteria=testing_criteria(deployment=args.deployment, full=args.full),
    )
    run = client.evals.runs.create(
        eval_id=eval_object.id,
        name=f"ntk-{label}-{datetime.now(UTC).strftime('%H%M')}",
        data_source=data_source(rows, agent=args.agent, version=args.version),
    )
    print(f"eval {eval_object.id}\nrun  {run.id}\nreport {run.report_url}")
    if args.no_wait:
        return 0
    started = time.monotonic()
    while True:
        run = client.evals.runs.retrieve(run_id=run.id, eval_id=eval_object.id)
        if run.status in ("completed", "failed", "canceled"):
            break
        print(f"  {run.status} · {time.monotonic() - started:.0f}s", file=sys.stderr)
        time.sleep(10)
    items = list(client.evals.runs.output_items.list(run_id=run.id, eval_id=eval_object.id))
    summary = summarize_items(items)
    result = {
        "label": label,
        "eval_id": eval_object.id,
        "run_id": run.id,
        "status": run.status,
        "report_url": run.report_url,
        "seconds": round(time.monotonic() - started),
        "summary": summary,
        "items": [it.model_dump() if hasattr(it, "model_dump") else it for it in items],
    }
    out = RESULTS / f"cloud-{label}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")
    print(f"status {run.status} in {result['seconds']} s · {len(items)} items")
    for name, s in summary.items():
        print(f"  {name:<20} pass {s['passed']}/{s['n']} ({s['pass_rate']:.0%})  mean {s['mean_score']}")
    if run.status == "failed" and getattr(run, "error", None):
        print(f"error: {run.error}")
    print(f"wrote {out.relative_to(ROOT)}")
    return 0 if run.status == "completed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
