"""The three agent tools (scenario spec §Agent design).

All three are deterministic and read only local fixtures: ``program_search``
and ``preferences`` are lookups, ``clash_checker`` is a pure function. They
return JSON strings so the model sees exactly what the evals will later score.
"""

from __future__ import annotations

import json
from typing import Any

from langchain_core.tools import tool

from agent import clash_checker as _clash
from agent.preferences import get_persona
from agent.program import load_program


def _json(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False)


@tool
def program_search(
    query: str = "",
    track: str | None = None,
    day: str | None = None,
    room: str | None = None,
    limit: int = 25,
) -> str:
    """Search the NT konferenca 2026 program.

    Args:
        query: Free-text keywords (Slovene or English; diacritics optional), e.g. "agenti langgraph".
            Leave empty to list everything that matches the filters.
        track: Optional track filter: AI, Azure, Varnost, Podatki, Razvoj, Microsoft 365,
            Infrastruktura, Poslovno (English aliases like "security" are accepted).
        day: Optional day filter: an ISO date (2026-09-22) or a weekday name (torek / tuesday).
        room: Optional room name filter.
        limit: Maximum number of results (default 25, max 80).

    Returns:
        JSON list of talks with id, title, speaker, room, start, end (ISO 8601), track, level,
        lang and day. Use the returned ids and times verbatim when building an agenda.
    """
    program = load_program()
    try:
        results = program.search(query, track=track, day=day, room=room, limit=limit)
    except ValueError as exc:
        return _json({"error": str(exc)})
    return _json(results)


@tool
def clash_checker(talk_ids: list[str]) -> str:
    """Check a candidate agenda for overlapping talks.

    Args:
        talk_ids: The ids of every talk in the proposed agenda (e.g. ["t-014", "t-021"]).

    Returns:
        JSON with clash_count, ok (true when there are no overlaps), the list of clashing pairs
        with overlap minutes, the resolved slots, and any unknown ids. An agenda is only valid
        when clash_count is 0 and unknown_ids is empty.
    """
    program = load_program()
    slots, unknown = program.slots(talk_ids or [])
    report = _clash.clash_report(slots)
    report["unknown_ids"] = unknown
    report["ok"] = report["ok"] and not unknown
    report["slots"] = [
        {"id": s["id"], "title": s["title"], "start": s["start"], "end": s["end"]} for s in slots
    ]
    return _json(report)


@tool
def preferences(attendee: str | None = None) -> str:
    """Read an attendee's profile: interests, preferred tracks, days and constraints.

    Args:
        attendee: Attendee id or first name. Omit to use the attendee this session is configured for.

    Returns:
        JSON profile with interests, tracks, days and constraints (earliest_start, latest_end,
        min_break_minutes, lunch_break, preferred_language) plus a short note in Slovene.
    """
    try:
        return _json(get_persona(attendee))
    except KeyError as exc:
        return _json({"error": str(exc)})


def default_tools() -> list:
    return [program_search, clash_checker, preferences]


__all__ = ["clash_checker", "default_tools", "preferences", "program_search"]
