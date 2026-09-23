"""Build (and register) the Foundry evaluators from the agent's own metric code.

Foundry code-based evaluators are a single Python ``grade(sample, item) -> float`` function
that runs in a sandbox with no network and no repo access. So the three code-based metrics
are *generated*: the source of ``src/agent/{clash_checker,metrics,contract}.py`` (pure stdlib)
is concatenated with the program fixture and a ``grade`` function, and the result is what gets
registered. The tool the agent calls and the metric the eval scores are therefore literally the
same code (scenario spec: "the metric and the tool can never disagree").

    uv run build-evaluators              # write evals/evaluators/<name>.py (deterministic)
    uv run build-evaluators --register   # also register every evaluator in the Foundry project
    uv run build-evaluators --check      # exit 1 when the generated files are stale

Data contract (what each dataset row must carry, see evals/README.md): ``query`` (the user
message), ``day`` (ISO date), ``earliest_start`` ("HH:MM" or ""), ``min_break_minutes`` (int),
``attendee`` (persona id). For agent-target runs the answer is ``item["sample"]["output_text"]``;
for query/response datasets it is ``item["response"]``.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
AGENT_DIR = ROOT / "src" / "agent"
OUT_DIR = ROOT / "evals" / "evaluators"
PROGRAM_PATH = ROOT / "fixtures" / "program.json"
MAX_CODE_BYTES = 256 * 1024  # sandbox limit (Learn, custom-evaluators, 2026-08)

CODE_EVALUATORS: dict[str, dict[str, str]] = {
    "ntk_clash_free": {
        "display_name": "NTK · clash-free agenda",
        "description": (
            "1.0 when the produced agenda has no overlapping talks (times resolved against the "
            "conference program), 1/(1+clashes) otherwise; capped at 0.5 when the agenda names "
            "talks that do not exist; 0.0 without a parsable agenda."
        ),
    },
    "ntk_preferences": {
        "display_name": "NTK · preference violations",
        "description": (
            "1.0 when no talk starts before the attendee's earliest hour and every talk is on the "
            "requested day, 1/(1+violations) otherwise; 0.0 without a parsable agenda."
        ),
    },
    "ntk_break_coverage": {
        "display_name": "NTK · coffee break coverage",
        "description": (
            "1.0 when the agenda leaves at least one free stretch of min_break_minutes "
            "(default 30) between 10:00 and 14:00 on the requested day, partial credit for a "
            "shorter longest gap; 0.0 without a parsable agenda."
        ),
    },
}

PROMPT_EVALUATORS: dict[str, dict[str, str]] = {
    "ntk_completeness": {
        "display_name": "NTK · completeness (judge)",
        "description": "LLM judge: are the requested day-parts and interests reflected in the agenda?",
        "prompt_text": (
            "You are grading a conference-agenda assistant for NT konferenca 2026 (Slovenia).\n"
            "The user asked (in Slovene):\n{{query}}\n\n"
            "The assistant answered:\n{{response}}\n\n"
            "Rate COMPLETENESS from 1 to 5: does the agenda cover the day-parts the user asked for "
            "(e.g. whole day, morning only, afternoon), reflect the interests/tracks they named, and "
            "respect explicit constraints (earliest hour, coffee gap, leaving early)?\n"
            "1 - ignores the request; 2 - mostly off; 3 - partially covered; 4 - covered with a minor "
            "gap; 5 - fully covered.\n\n"
            'Output Format (JSON):\n{\n  "result": <integer from 1 to 5>,\n'
            '  "reason": "<brief explanation>"\n}\n'
        ),
    },
    "ntk_language": {
        "display_name": "NTK · Slovene register (judge)",
        "description": "LLM judge: is the narrative fully in Slovene, friendly but professional?",
        "prompt_text": (
            "You are grading the language of a conference-agenda assistant's answer.\n"
            "The user asked:\n{{query}}\n\nThe assistant answered:\n{{response}}\n\n"
            "Ignore the JSON block; judge only the prose. Rate LANGUAGE from 1 to 5: is the prose "
            "entirely in Slovene (no English sentences except product names), grammatical, and in a "
            "friendly-formal register suitable for a conference attendee?\n"
            "1 - not Slovene; 2 - mostly another language; 3 - Slovene with clear errors or wrong "
            "register; 4 - good Slovene, small slips; 5 - natural, correct, friendly-formal Slovene.\n\n"
            'Output Format (JSON):\n{\n  "result": <integer from 1 to 5>,\n'
            '  "reason": "<brief explanation>"\n}\n'
        ),
    },
}

_TZ_LINE = 'DEFAULT_TZ = ZoneInfo("Europe/Ljubljana")'
_TZ_SAFE = """try:
    DEFAULT_TZ = ZoneInfo("Europe/Ljubljana")
except Exception:  # no tz database in the evaluator sandbox: September in Slovenia is CEST
    from datetime import timedelta as _td
    from datetime import timezone as _tz

    DEFAULT_TZ = _tz(_td(hours=2))"""

_HEADER = '''"""GENERATED by scripts/build_evaluators.py — do not edit; edit src/agent/*.py instead.

Foundry code-based evaluator: {name}
{description}
"""

from __future__ import annotations
'''

_COMMON_TAIL = '''

# ---------------------------------------------------------------------------
# Evaluator glue (shared by the three NTK evaluators)
# ---------------------------------------------------------------------------

PROGRAM_JSON = r"""{program_json}"""
_PROGRAM = {{talk["id"]: talk for talk in json.loads(PROGRAM_JSON)}}


def _text_of(value):
    """A str as-is; a Responses-style output_items list (or message list) flattened to its text."""
    if isinstance(value, str):
        return value if value.strip() else ""
    if isinstance(value, dict):
        value = [value]
    if isinstance(value, list):
        chunks = []
        for entry in value:
            if isinstance(entry, str):
                chunks.append(entry)
            elif isinstance(entry, dict):
                content = entry.get("content")
                if isinstance(content, str):
                    chunks.append(content)
                for part in content if isinstance(content, list) else []:
                    if isinstance(part, dict) and isinstance(part.get("text"), str):
                        chunks.append(part["text"])
                if isinstance(entry.get("text"), str):
                    chunks.append(entry["text"])
        return "\\n".join(c for c in chunks if c.strip())
    return ""


def _answer_text(item):
    """The agent's answer, wherever the run put it.

    Explicit data_mapping (scripts/eval_cloud.py): ``item["response"]`` = ``{{sample.output_text}}``.
    azd's agent-style mapping: ``item["response"]`` = ``{{sample.output_items}}`` (a list).
    No mapping: ``item["sample"]["output_text"]`` / ``["output_items"]``.
    """
    if not isinstance(item, dict):
        return ""
    for key in ("response", "output_text", "answer"):
        text = _text_of(item.get(key))
        if text:
            return text
    sample = item.get("sample")
    if isinstance(sample, dict):
        for key in ("output_text", "output_items", "output"):
            text = _text_of(sample.get(key))
            if text:
                return text
    return ""


def _normalize_item(item, sample=None):
    """Flatten the shapes an eval run can hand over.

    ``item`` may be the dataset row, a dict of mapped fields (with the row nested under ``item``
    or ``row``), or a mix; ``sample`` may carry the agent output separately. Mapped top-level
    fields win over the nested row.
    """
    if not isinstance(item, dict):
        item = {{}}
    merged = dict(item)
    for key in ("item", "row"):
        nested = item.get(key)
        if isinstance(nested, dict):
            merged = {{**nested, **{{k: v for k, v in merged.items() if k != key}}}}
    if isinstance(sample, dict) and sample and not isinstance(merged.get("sample"), dict):
        merged["sample"] = sample
    return merged


def _resolved_agenda(item):
    """Agenda items with program data applied, plus unknown ids; None when unparsable."""
    agenda = extract_agenda(_answer_text(item))
    if agenda is None:
        return None
    resolved = resolve_items(agenda, _PROGRAM.get)
    return resolved


def _requested_day(item, agenda):
    day = item.get("day") if isinstance(item, dict) else None
    if not day and isinstance(agenda, dict):
        day = agenda.get("day")
    return str(day) if day else None


def _prefs(item):
    if not isinstance(item, dict):
        return Preferences()
    earliest = item.get("earliest_start") or None
    latest = item.get("latest_end") or None
    gap = item.get("min_break_minutes")
    try:
        gap = int(gap) if gap not in (None, "") else None
    except (TypeError, ValueError):
        gap = None
    return Preferences(
        earliest_start=_parse_time(earliest),
        latest_end=_parse_time(latest),
        min_break_minutes=gap,
    )


def _clamp(value):
    return max(0.0, min(1.0, float(value)))
'''

_GRADES: dict[str, str] = {
    "ntk_clash_free": '''

def grade(sample: dict, item: dict) -> float:
    """1.0 for a clash-free agenda, 1/(1+clashes) otherwise; unknown talk ids cap the score at 0.5."""
    try:
        item = _normalize_item(item, sample)
        agenda = _resolved_agenda(item)
        if agenda is None or not agenda.get("items"):
            return 0.0
        clashes = clash_count(agenda["items"])
        score = 1.0 / (1.0 + clashes)
        if agenda.get("unknown_ids"):
            score = min(score, 0.5)
        return _clamp(score)
    except Exception:
        return 0.0
''',
    "ntk_preferences": '''

def grade(sample: dict, item: dict) -> float:
    """1.0 when no talk starts before the earliest hour and all talks are on the requested day."""
    try:
        item = _normalize_item(item, sample)
        agenda = _resolved_agenda(item)
        if agenda is None or not agenda.get("items"):
            return 0.0
        report = preference_violations(agenda["items"], _prefs(item), day=_requested_day(item, agenda))
        violations = len(report["before_earliest"]) + len(report["off_day"]) + len(report["after_latest"])
        return _clamp(1.0 / (1.0 + violations))
    except Exception:
        return 0.0
''',
    "ntk_break_coverage": '''

def grade(sample: dict, item: dict) -> float:
    """1.0 with a free stretch of min_break_minutes between 10:00 and 14:00, partial credit otherwise."""
    try:
        item = _normalize_item(item, sample)
        agenda = _resolved_agenda(item)
        if agenda is None or not agenda.get("items"):
            return 0.0
        prefs = _prefs(item)
        min_gap = prefs.min_break_minutes or DEFAULT_MIN_GAP_MINUTES
        day = _requested_day(item, agenda)
        requested = date.fromisoformat(day) if day else None
        report = break_coverage(agenda["items"], day=requested, min_gap_minutes=min_gap)
        if report["ok"]:
            return 1.0
        return _clamp(min(0.9, report["longest_gap_minutes"] / float(min_gap)))
    except Exception:
        return 0.0
''',
}


def _module_source(name: str) -> str:
    text = (AGENT_DIR / f"{name}.py").read_text(encoding="utf-8")
    text = re.sub(r"^from __future__ import annotations\n", "", text, flags=re.MULTILINE)
    text = re.sub(r"^from agent\.[a-z_]+ import [^\n]+\n", "", text, flags=re.MULTILINE)
    if name == "clash_checker":
        if _TZ_LINE not in text:
            raise RuntimeError("clash_checker.py no longer defines DEFAULT_TZ the way the builder expects")
        text = text.replace(_TZ_LINE, _TZ_SAFE)
    return text


def compact_program() -> list[dict[str, str]]:
    """The fields the evaluators need (times, rooms, titles); tags/abstracts stay out to save bytes."""
    data = json.loads(PROGRAM_PATH.read_text(encoding="utf-8"))
    keep = ("id", "title", "room", "start", "end", "track", "speaker")
    return [{k: talk[k] for k in keep if k in talk} for talk in data["talks"]]


def build(name: str) -> str:
    """The complete, self-contained code_text for one code-based evaluator."""
    if name not in CODE_EVALUATORS:
        raise KeyError(name)
    parts = [_HEADER.format(name=name, description=CODE_EVALUATORS[name]["description"])]
    parts.append("import json  # noqa: E402  (evaluator glue)\n")
    for module in ("clash_checker", "metrics", "contract"):
        parts.append(f"\n# ===== src/agent/{module}.py =====\n")
        parts.append(_module_source(module))
    program_json = json.dumps(compact_program(), ensure_ascii=False, separators=(",", ":"))
    parts.append(_COMMON_TAIL.format(program_json=program_json))
    parts.append(_GRADES[name])
    code = "".join(parts)
    if len(code.encode("utf-8")) >= MAX_CODE_BYTES:
        raise RuntimeError(
            f"{name}: code_text is {len(code.encode())} bytes, sandbox limit is {MAX_CODE_BYTES}"
        )
    return code


def write_all() -> dict[str, Path]:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    written = {}
    for name in CODE_EVALUATORS:
        path = OUT_DIR / f"{name}.py"
        path.write_text(build(name), encoding="utf-8")
        written[name] = path
    for name, spec in PROMPT_EVALUATORS.items():
        path = OUT_DIR / f"{name}.prompt.md"
        path.write_text(spec["prompt_text"], encoding="utf-8")
        written[name] = path
    return written


def check_all() -> list[str]:
    stale = []
    for name in CODE_EVALUATORS:
        path = OUT_DIR / f"{name}.py"
        if not path.exists() or path.read_text(encoding="utf-8") != build(name):
            stale.append(str(path))
    for name, spec in PROMPT_EVALUATORS.items():
        path = OUT_DIR / f"{name}.prompt.md"
        if not path.exists() or path.read_text(encoding="utf-8") != spec["prompt_text"]:
            stale.append(str(path))
    return stale


# The fields the graders read. An eval run maps them with data_mapping (scripts/eval_cloud.py):
# query/day/earliest_start/min_break_minutes/attendee from the dataset row ({{item.<field>}}) and
# response from the agent's answer ({{sample.output_text}}). Nothing is *required* so a bare
# reference (azd) still validates the definition; grade() copes with whatever arrives.
DATA_FIELDS = (
    "query",
    "response",
    "attendee",
    "day",
    "earliest_start",
    "latest_end",
    "min_break_minutes",
)
DATA_SCHEMA = {
    "type": "object",
    "required": [],
    "properties": {
        "query": {"type": "string"},
        "response": {"type": "string"},
        "attendee": {"type": "string"},
        "day": {"type": "string"},
        "earliest_start": {"type": "string"},
        "latest_end": {"type": "string"},
        "min_break_minutes": {"type": "number"},
    },
}


def data_mapping() -> dict[str, str]:
    """The data_mapping an eval run passes so the graders see row fields + the agent's answer.

    Foundry insists on an ``item`` mapping for code-based evaluators whatever the data_schema says
    ("Data mapping for required field 'item' is missing", verified 2026-09-06); the row fields and
    the answer are mapped alongside it and ``_normalize_item`` in the generated code merges both.
    """
    # Mapping values must match {{item.<field>}} / {{sample.<field>}} (bare {{item}} is rejected),
    # so eval_cloud.py nests a copy of every dataset row under "row" and maps item to it.
    mapping = {"item": "{{item.row}}"}
    mapping.update({field: f"{{{{item.{field}}}}}" for field in DATA_FIELDS if field != "response"})
    mapping["response"] = "{{sample.output_text}}"
    return mapping


def code_definition(name: str) -> dict:
    # Learn says deployment_name + pass_threshold are required init parameters, but
    # `azd ai agent eval run` references custom evaluators bare (no initialization_parameters,
    # no data_mapping) and the service then rejects the run with MissingRequiredParameter /
    # MissingRequiredDataMapping (verified 2026-09-06, the talk's write-up (D-20)). Declaring nothing as
    # required is what makes the azd path work; grade() reads item/sample defensively anyway.
    return {
        "type": "code",
        "code_text": build(name),
        "init_parameters": {
            "type": "object",
            "properties": {"deployment_name": {"type": "string"}, "pass_threshold": {"type": "number"}},
            "required": [],
        },
        "metrics": {
            "result": {
                "type": "continuous",
                "desirable_direction": "increase",
                "min_value": 0.0,
                "max_value": 1.0,
                "threshold": 1.0,
                "is_primary": True,
            }
        },
        "data_schema": DATA_SCHEMA,
    }


def prompt_definition(name: str) -> dict:
    return {
        "type": "prompt",
        "prompt_text": PROMPT_EVALUATORS[name]["prompt_text"],
        "init_parameters": {
            "type": "object",
            "properties": {"deployment_name": {"type": "string"}, "threshold": {"type": "number"}},
            "required": [],  # same azd constraint as code_definition()
        },
        "data_schema": {
            "type": "object",
            "properties": {"query": {"type": "string"}, "response": {"type": "string"}},
            "required": [],
        },
        "metrics": {
            "result": {
                "type": "ordinal",
                "desirable_direction": "increase",
                "min_value": 1,
                "max_value": 5,
                "threshold": 4,
                "is_primary": True,
            }
        },
    }


def register() -> dict[str, str]:
    """Register every evaluator as a new version in the Foundry project; returns name → version."""
    import os

    from azure.ai.projects import AIProjectClient
    from azure.identity import DefaultAzureCredential

    from scripts.azdenv import load_env

    load_env(ROOT)
    endpoint = os.environ.get("FOUNDRY_PROJECT_ENDPOINT", "").rstrip("/")
    if not endpoint:
        sys.exit("FOUNDRY_PROJECT_ENDPOINT is not set (azd env get-values, or .env)")
    client = AIProjectClient(endpoint=endpoint, credential=DefaultAzureCredential())
    versions: dict[str, str] = {}
    specs = [(n, s, code_definition(n)) for n, s in CODE_EVALUATORS.items()]
    specs += [(n, s, prompt_definition(n)) for n, s in PROMPT_EVALUATORS.items()]
    for name, spec, definition in specs:
        created = client.beta.evaluators.create_version(
            name=name,
            evaluator_version={
                "name": name,
                "evaluator_type": "custom",
                "categories": ["quality"],
                "display_name": spec["display_name"],
                "description": spec["description"],
                "definition": definition,
            },
        )
        versions[name] = str(created.get("version"))
        print(f"registered {name:<20} version {versions[name]:<4} ({definition['type']})")
    (ROOT / "evals" / "registered.json").write_text(json.dumps(versions, indent=2) + "\n", encoding="utf-8")
    return versions


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate (and register) the NTK Foundry evaluators")
    parser.add_argument(
        "--register", action="store_true", help="register new versions in the Foundry project"
    )
    parser.add_argument("--check", action="store_true", help="fail when evals/evaluators/ is out of date")
    args = parser.parse_args(argv)
    if args.check:
        stale = check_all()
        if stale:
            print("stale generated evaluators (run `uv run build-evaluators`):", *stale, sep="\n  ")
            return 1
        print("evaluators up to date")
        return 0
    for name, path in write_all().items():
        print(f"wrote {path.relative_to(ROOT)}  ({path.stat().st_size:,} bytes)  [{name}]")
    if args.register:
        register()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
