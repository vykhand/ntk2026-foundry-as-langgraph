"""Attendee profiles (fictional personas from ``fixtures/personas.json``)."""

from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PERSONAS_PATH = ROOT / "fixtures" / "personas.json"
DEFAULT_ATTENDEE = "maja"


@lru_cache(maxsize=4)
def _load(path_str: str) -> dict[str, Any]:
    return json.loads(Path(path_str).read_text(encoding="utf-8"))


def load_personas(path: str | os.PathLike[str] | None = None) -> dict[str, Any]:
    chosen = Path(path or os.environ.get("NTK_PERSONAS_PATH") or DEFAULT_PERSONAS_PATH)
    if not chosen.is_absolute():
        chosen = ROOT / chosen
    return _load(str(chosen.resolve()))


def default_attendee() -> str:
    return os.environ.get("NTK_ATTENDEE") or DEFAULT_ATTENDEE


def get_persona(attendee: str | None = None) -> dict[str, Any]:
    """Return the profile for *attendee* (default: ``NTK_ATTENDEE``); raise if unknown."""
    wanted = (attendee or default_attendee()).strip().casefold()
    personas = load_personas()["attendees"]
    for persona in personas:
        if persona["id"].casefold() == wanted or persona.get("name", "").casefold() == wanted:
            return persona
    known = ", ".join(p["id"] for p in personas)
    raise KeyError(f"neznan udeleženec {attendee!r}; znani profili: {known}")


__all__ = ["DEFAULT_ATTENDEE", "default_attendee", "get_persona", "load_personas"]
