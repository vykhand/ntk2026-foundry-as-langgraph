"""Code-based agenda metrics (scenario spec §Eval metrics).

All three live-run metrics are pure functions over the structured agenda, so
the eval can never disagree with the tool the agent used:

* **Clash count** — delegated to :mod:`agent.clash_checker`.
* **Preference violations** — talks before the attendee's earliest hour or
  after their latest hour, plus a missing requested coffee gap.
* **Break coverage** — at least one free stretch of ``min_gap_minutes``
  inside the 10:00–14:00 window.

The two LLM-judge metrics (completeness, language) are *not* here; they belong
to the cached full eval run and are configured in ``evals/``.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import date, datetime, time
from typing import Any
from zoneinfo import ZoneInfo

from agent.clash_checker import DEFAULT_TZ, Slot, clash_report, normalize

BREAK_WINDOW: tuple[time, time] = (time(10, 0), time(14, 0))
DEFAULT_MIN_GAP_MINUTES = 30


def _parse_time(value: str | time | None) -> time | None:
    if value in (None, ""):
        return None
    if isinstance(value, time):
        return value
    hours, _, minutes = str(value).partition(":")
    return time(int(hours), int(minutes or 0))


@dataclass(frozen=True, slots=True)
class Preferences:
    """The subset of an attendee profile the code-based metrics understand."""

    earliest_start: time | None = None
    latest_end: time | None = None
    min_break_minutes: int | None = None

    @classmethod
    def from_persona(cls, persona: Mapping[str, Any]) -> Preferences:
        """Read ``constraints`` from a ``fixtures/personas.json`` entry (or a flat dict)."""
        constraints = persona.get("constraints", persona)
        raw_gap = constraints.get("min_break_minutes")
        return cls(
            earliest_start=_parse_time(constraints.get("earliest_start")),
            latest_end=_parse_time(constraints.get("latest_end")),
            min_break_minutes=int(raw_gap) if raw_gap not in (None, "") else None,
        )


def _local(dt: datetime, tz: ZoneInfo) -> datetime:
    return dt.astimezone(tz)


def _agenda_days(slots: list[Slot], tz: ZoneInfo) -> list[date]:
    return sorted({_local(s.start, tz).date() for s in slots})


def free_intervals(
    slots: Iterable[Slot | Mapping[str, Any]],
    *,
    day: date | None = None,
    window: tuple[time, time] = BREAK_WINDOW,
    tz: ZoneInfo = DEFAULT_TZ,
) -> list[tuple[datetime, datetime]]:
    """Free stretches inside ``window`` on ``day`` (default: the agenda's first day)."""
    normalized = normalize(slots)
    if day is None:
        days = _agenda_days(normalized, tz)
        if not days:
            return []
        day = days[0]
    win_start = datetime.combine(day, window[0], tzinfo=tz)
    win_end = datetime.combine(day, window[1], tzinfo=tz)
    cursor = win_start
    gaps: list[tuple[datetime, datetime]] = []
    for slot in normalized:  # already sorted by start
        start, end = max(slot.start, win_start), min(slot.end, win_end)
        if end <= win_start or start >= win_end:
            continue
        if start > cursor:
            gaps.append((cursor, start))
        cursor = max(cursor, end)
    if cursor < win_end:
        gaps.append((cursor, win_end))
    return gaps


def break_coverage(
    slots: Iterable[Slot | Mapping[str, Any]],
    *,
    day: date | None = None,
    window: tuple[time, time] = BREAK_WINDOW,
    min_gap_minutes: int = DEFAULT_MIN_GAP_MINUTES,
    tz: ZoneInfo = DEFAULT_TZ,
) -> dict[str, Any]:
    """Is there at least one gap of ``min_gap_minutes`` between 10:00 and 14:00?"""
    normalized = normalize(slots)
    days = _agenda_days(normalized, tz)
    if day is None and days:
        day = days[0]
    gaps = free_intervals(normalized, day=day, window=window, tz=tz) if day else []
    minutes = [int((b - a).total_seconds() // 60) for a, b in gaps]
    longest = max(minutes, default=0)
    talks_in_window = 0
    if day:
        win_start = datetime.combine(day, window[0], tzinfo=tz)
        win_end = datetime.combine(day, window[1], tzinfo=tz)
        talks_in_window = sum(1 for s in normalized if s.start < win_end and s.end > win_start)
    return {
        "ok": longest >= min_gap_minutes,
        "day": day.isoformat() if day else None,
        "window": [window[0].strftime("%H:%M"), window[1].strftime("%H:%M")],
        "min_gap_minutes": min_gap_minutes,
        "longest_gap_minutes": longest,
        "talks_in_window": talks_in_window,
        "gaps": [
            {"start": a.isoformat(), "end": b.isoformat(), "minutes": m}
            for (a, b), m in zip(gaps, minutes, strict=True)
        ],
    }


def preference_violations(
    slots: Iterable[Slot | Mapping[str, Any]],
    prefs: Preferences | Mapping[str, Any],
    *,
    day: date | str | None = None,
    tz: ZoneInfo = DEFAULT_TZ,
) -> dict[str, Any]:
    """Talks outside the attendee's hours, off the requested day, and a missing coffee gap."""
    if not isinstance(prefs, Preferences):
        prefs = Preferences.from_persona(prefs)
    normalized = normalize(slots)
    requested = date.fromisoformat(day) if isinstance(day, str) else day
    off_day = [s.id for s in normalized if requested and _local(s.start, tz).date() != requested]
    before = [
        s.id
        for s in normalized
        if prefs.earliest_start is not None and _local(s.start, tz).time() < prefs.earliest_start
    ]
    after = [
        s.id
        for s in normalized
        if prefs.latest_end is not None
        and (
            _local(s.end, tz).time() > prefs.latest_end
            or _local(s.end, tz).date() > _local(s.start, tz).date()
        )
    ]
    missing_break = False
    if prefs.min_break_minutes:
        missing_break = any(
            not break_coverage(normalized, day=d, min_gap_minutes=prefs.min_break_minutes, tz=tz)[
                "ok"
            ]
            for d in _agenda_days(normalized, tz)
        )
    count = len(before) + len(after) + len(off_day) + (1 if missing_break else 0)
    return {
        "count": count,
        "ok": count == 0,
        "before_earliest": before,
        "after_latest": after,
        "off_day": off_day,
        "requested_day": requested.isoformat() if requested else None,
        "missing_break": missing_break,
        "earliest_start": prefs.earliest_start.strftime("%H:%M") if prefs.earliest_start else None,
        "latest_end": prefs.latest_end.strftime("%H:%M") if prefs.latest_end else None,
        "min_break_minutes": prefs.min_break_minutes,
    }


def evaluate_agenda(
    slots: Iterable[Slot | Mapping[str, Any]],
    prefs: Preferences | Mapping[str, Any] | None = None,
    *,
    day: date | str | None = None,
    tz: ZoneInfo = DEFAULT_TZ,
) -> dict[str, Any]:
    """All three code-based metrics in one JSON-serialisable dict.

    ``day`` is the day the attendee asked for; when given, break coverage is measured on that
    day and talks scheduled on any other day count as preference violations (an agenda spread
    over several days would otherwise be trivially clash-free).
    """
    normalized = normalize(slots)
    requested = date.fromisoformat(day) if isinstance(day, str) else day
    clashes = clash_report(normalized)
    coverage = break_coverage(normalized, day=requested, tz=tz)
    violations = preference_violations(normalized, prefs or Preferences(), day=requested, tz=tz)
    return {
        "items": len(normalized),
        "clash_count": clashes["clash_count"],
        "clashes": clashes["clashes"],
        "preference_violations": violations,
        "break_coverage": coverage,
        "ok": clashes["ok"] and violations["ok"] and coverage["ok"],
    }


__all__ = [
    "BREAK_WINDOW",
    "DEFAULT_MIN_GAP_MINUTES",
    "Preferences",
    "break_coverage",
    "evaluate_agenda",
    "free_intervals",
    "preference_violations",
]
