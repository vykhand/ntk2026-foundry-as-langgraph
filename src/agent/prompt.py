"""System prompt loading (see ``prompts/README.md`` for precedence and the engineered baseline)."""

from __future__ import annotations

import os
from pathlib import Path

from agent.preferences import default_attendee
from agent.program import load_program

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PROMPT_FILE = "prompts/baseline_v1.md"


def prompt_source() -> str:
    """Human-readable description of where the active prompt comes from (for logs/slides)."""
    if os.environ.get("NTK_SYSTEM_PROMPT"):
        return "env:NTK_SYSTEM_PROMPT"
    return os.environ.get("NTK_PROMPT_FILE") or DEFAULT_PROMPT_FILE


def load_prompt_text() -> str:
    text = os.environ.get("NTK_SYSTEM_PROMPT")
    if text:
        return text.strip()
    rel = os.environ.get("NTK_PROMPT_FILE") or DEFAULT_PROMPT_FILE
    path = Path(rel)
    if not path.is_absolute():
        path = ROOT / path
    return path.read_text(encoding="utf-8").strip()


def context_block() -> str:
    """Facts the model needs regardless of prompt version: conference days and the session's attendee."""
    program = load_program()
    days = ", ".join(f"{label} = {day}" for day, label in program.day_labels().items())
    return (
        "\n\n## Kontekst\n"
        f"- Konferenca: {program.meta.get('conference', 'NT konferenca 2026')}, "
        f"{program.meta.get('venue', 'Portorož')}.\n"
        f"- Dnevi: {days}.\n"
        f"- Privzeti udeleženec te seje: `{default_attendee()}`.\n"
    )


def load_system_prompt() -> str:
    """The tracked prompt plus the generated context block."""
    return load_prompt_text() + context_block()


__all__ = ["DEFAULT_PROMPT_FILE", "context_block", "load_prompt_text", "load_system_prompt", "prompt_source"]
