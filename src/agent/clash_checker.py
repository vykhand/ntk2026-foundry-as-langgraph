"""Deterministic clash detection for a candidate agenda.

This is the keystone of the demo: it is both an agent tool (via
``agent.tools.clash_checker``) and the headline eval metric. Because the same
pure function serves both roles, the tool and the metric can never disagree.

Semantics
---------
* A slot is a half-open interval ``[start, end)``. Two slots clash when
  ``a.start < b.end and b.start < a.end``; touching boundaries (one ends
  exactly when the next begins) are *not* a clash.
* Times are ISO 8601 strings or ``datetime`` objects. Naive values are
  interpreted in ``Europe/Ljubljana``; aware values are compared on the
  absolute timeline, so mixed offsets are fine.
* Duplicate ids are collapsed to the first occurrence — listing the same
  talk twice is a duplication error, not a clash.
* Malformed slots (missing times, ``end <= start``) raise ``ValueError``
  with a message that names the offending slot.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

DEFAULT_TZ = ZoneInfo("Europe/Ljubljana")


@dataclass(frozen=True, slots=True)
class Slot:
    """A scheduled item on an agenda."""

    id: str
    start: datetime
    end: datetime
    title: str = ""
    room: str = ""

    @property
    def minutes(self) -> int:
        return int((self.end - self.start).total_seconds() // 60)


@dataclass(frozen=True, slots=True)
class Clash:
    """Two agenda items that overlap in time."""

    a: str
    b: str
    overlap_minutes: int
    a_title: str = ""
    b_title: str = ""
    a_room: str = ""
    b_room: str = ""

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def parse_dt(value: str | datetime | None, *, tz: ZoneInfo = DEFAULT_TZ) -> datetime:
    """Parse an ISO 8601 string (or pass through a datetime); localize naive values."""
    if isinstance(value, datetime):
        dt = value
    elif isinstance(value, str) and value.strip():
        text = value.strip().replace("Z", "+00:00")
        try:
            dt = datetime.fromisoformat(text)
        except ValueError as exc:
            raise ValueError(f"not an ISO 8601 datetime: {value!r}") from exc
    else:
        raise ValueError(f"missing or invalid datetime: {value!r}")
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=tz)
    return dt


def to_slot(item: object, *, index: int = 0) -> Slot:
    """Coerce a mapping (``{"id", "start", "end", ...}``) into a :class:`Slot`."""
    if isinstance(item, Slot):
        slot = item
    elif isinstance(item, Mapping):
        raw_id = item.get("id")
        slot_id = str(raw_id) if raw_id not in (None, "") else f"item-{index}"
        try:
            start = parse_dt(item.get("start"))
            end = parse_dt(item.get("end"))
        except ValueError as exc:
            raise ValueError(f"slot {slot_id!r}: {exc}") from exc
        slot = Slot(
            id=slot_id,
            start=start,
            end=end,
            title=str(item.get("title") or ""),
            room=str(item.get("room") or ""),
        )
    else:
        raise ValueError(f"slot #{index}: expected a mapping or Slot, got {type(item).__name__}")
    if slot.end <= slot.start:
        raise ValueError(f"slot {slot.id!r}: end ({slot.end.isoformat()}) is not after start")
    return slot


def normalize(items: Iterable[Slot | Mapping[str, Any]]) -> list[Slot]:
    """Validate, deduplicate by id (first wins) and sort by start time."""
    seen: set[str] = set()
    slots: list[Slot] = []
    for index, item in enumerate(items):
        slot = to_slot(item, index=index)
        if slot.id in seen:
            continue
        seen.add(slot.id)
        slots.append(slot)
    slots.sort(key=lambda s: (s.start, s.end, s.id))
    return slots


def overlap_minutes(a: Slot, b: Slot) -> int:
    """Length of the intersection of two slots in whole minutes (0 when disjoint)."""
    latest_start = max(a.start, b.start)
    earliest_end = min(a.end, b.end)
    seconds = (earliest_end - latest_start).total_seconds()
    return int(seconds // 60) if seconds > 0 else 0


def find_clashes(items: Iterable[Slot | Mapping[str, Any]]) -> list[Clash]:
    """Return every overlapping pair in *items*, ordered by the earlier slot.

    Uses a sweep over the start-sorted list: for each slot, only later slots
    that start before it ends can overlap, so the scan stops at the first
    non-overlapping successor. Overlap is strict — touching boundaries do not
    count.
    """
    slots = normalize(items)
    clashes: list[Clash] = []
    for i, a in enumerate(slots):
        for b in slots[i + 1 :]:
            if b.start >= a.end:
                break  # everything after b starts even later
            clashes.append(
                Clash(
                    a=a.id,
                    b=b.id,
                    overlap_minutes=overlap_minutes(a, b),
                    a_title=a.title,
                    b_title=b.title,
                    a_room=a.room,
                    b_room=b.room,
                )
            )
    return clashes


def clash_count(items: Iterable[Slot | Mapping[str, Any]]) -> int:
    """Number of overlapping pairs — the headline eval metric (target: 0)."""
    return len(find_clashes(items))


def clash_report(items: Iterable[Slot | Mapping[str, Any]]) -> dict[str, Any]:
    """JSON-serialisable summary used by the tool wrapper and the evals."""
    clashes = find_clashes(items)
    return {
        "clash_count": len(clashes),
        "ok": not clashes,
        "clashes": [c.as_dict() for c in clashes],
    }


__all__ = [
    "DEFAULT_TZ",
    "Clash",
    "Slot",
    "clash_count",
    "clash_report",
    "find_clashes",
    "normalize",
    "overlap_minutes",
    "parse_dt",
    "to_slot",
]
