"""Unit tests for the keystone tool/metric: agent.clash_checker."""

from __future__ import annotations

import random
from datetime import UTC, datetime, timedelta
from itertools import combinations
from zoneinfo import ZoneInfo

import pytest

from agent.clash_checker import (
    DEFAULT_TZ,
    Slot,
    clash_count,
    clash_report,
    find_clashes,
    normalize,
    overlap_minutes,
    parse_dt,
)

DAY = "2026-09-22"


def slot(id_: str, start: str, end: str, **extra) -> dict:
    return {"id": id_, "start": f"{DAY}T{start}:00+02:00", "end": f"{DAY}T{end}:00+02:00", **extra}


# ── parse_dt ────────────────────────────────────────────────────────────────


def test_parse_dt_keeps_offset():
    dt = parse_dt("2026-09-22T09:00:00+02:00")
    assert dt.utcoffset() == timedelta(hours=2)


def test_parse_dt_localizes_naive_to_ljubljana():
    dt = parse_dt("2026-09-22T09:00:00")
    assert dt.tzinfo is DEFAULT_TZ
    assert dt.utcoffset() == timedelta(hours=2)  # CEST in September


def test_parse_dt_accepts_zulu_and_datetime():
    assert parse_dt("2026-09-22T07:00:00Z") == datetime(2026, 9, 22, 7, tzinfo=UTC)
    raw = datetime(2026, 9, 22, 9, 0, tzinfo=ZoneInfo("Europe/Ljubljana"))
    assert parse_dt(raw) is raw


@pytest.mark.parametrize("bad", ["", None, "torek ob devetih", "2026-13-40T00:00"])
def test_parse_dt_rejects_garbage(bad):
    with pytest.raises(ValueError):
        parse_dt(bad)


# ── find_clashes semantics ──────────────────────────────────────────────────


def test_no_clash_when_sequential():
    agenda = [slot("a", "09:00", "09:45"), slot("b", "10:00", "10:45")]
    assert find_clashes(agenda) == []
    assert clash_count(agenda) == 0


def test_touching_boundaries_are_not_a_clash():
    agenda = [slot("a", "09:00", "10:00"), slot("b", "10:00", "10:45")]
    assert clash_count(agenda) == 0


def test_partial_overlap_is_a_clash_with_minutes():
    agenda = [slot("a", "09:00", "10:00"), slot("b", "09:30", "10:15")]
    clashes = find_clashes(agenda)
    assert len(clashes) == 1
    assert (clashes[0].a, clashes[0].b, clashes[0].overlap_minutes) == ("a", "b", 30)


def test_containment_is_a_clash():
    agenda = [slot("outer", "09:00", "12:00"), slot("inner", "10:00", "10:45")]
    clashes = find_clashes(agenda)
    assert [(c.a, c.b) for c in clashes] == [("outer", "inner")]
    assert clashes[0].overlap_minutes == 45


def test_one_minute_overlap_counts():
    agenda = [slot("a", "09:00", "10:01"), slot("b", "10:00", "10:45")]
    assert clash_count(agenda) == 1
    assert find_clashes(agenda)[0].overlap_minutes == 1


def test_three_way_overlap_reports_every_pair():
    agenda = [slot("a", "09:00", "10:00"), slot("b", "09:15", "10:15"), slot("c", "09:30", "10:30")]
    pairs = {(c.a, c.b) for c in find_clashes(agenda)}
    assert pairs == {("a", "b"), ("a", "c"), ("b", "c")}
    assert clash_count(agenda) == 3


def test_order_of_input_does_not_matter():
    agenda = [slot("late", "11:00", "11:45"), slot("early", "09:00", "10:00"), slot("mid", "09:30", "10:30")]
    clashes = find_clashes(agenda)
    assert [(c.a, c.b) for c in clashes] == [("early", "mid")]


def test_duplicate_ids_are_collapsed_not_clashed():
    agenda = [slot("a", "09:00", "09:45"), slot("a", "09:00", "09:45")]
    assert clash_count(agenda) == 0
    assert [s.id for s in normalize(agenda)] == ["a"]


def test_mixed_offsets_compare_on_absolute_timeline():
    agenda = [
        {"id": "utc", "start": "2026-09-22T07:00:00Z", "end": "2026-09-22T08:00:00Z"},
        slot("cest", "09:30", "10:15"),  # 07:30–08:15 UTC → overlaps by 30 min
    ]
    clashes = find_clashes(agenda)
    assert len(clashes) == 1 and clashes[0].overlap_minutes == 30


def test_naive_times_are_treated_as_local():
    agenda = [
        {"id": "naive", "start": "2026-09-22T09:00:00", "end": "2026-09-22T10:00:00"},
        slot("aware", "09:45", "10:30"),
    ]
    assert clash_count(agenda) == 1


def test_titles_and_rooms_are_carried_into_the_report():
    agenda = [
        slot("a", "09:00", "10:00", title="Agenti v praksi", room="Emerald"),
        slot("b", "09:30", "10:15", title="AKS v letu 2026", room="Adria"),
    ]
    report = clash_report(agenda)
    assert report["clash_count"] == 1 and report["ok"] is False
    c = report["clashes"][0]
    assert c["a_title"] == "Agenti v praksi" and c["b_room"] == "Adria"


def test_empty_and_single_item_agendas_are_ok():
    assert clash_report([]) == {"clash_count": 0, "ok": True, "clashes": []}
    assert clash_count([slot("a", "09:00", "09:45")]) == 0


def test_slot_objects_are_accepted_directly():
    a = Slot("a", parse_dt(f"{DAY}T09:00+02:00"), parse_dt(f"{DAY}T10:00+02:00"))
    b = Slot("b", parse_dt(f"{DAY}T09:30+02:00"), parse_dt(f"{DAY}T10:30+02:00"))
    assert overlap_minutes(a, b) == 30
    assert clash_count([a, b]) == 1


def test_missing_id_gets_a_positional_fallback():
    agenda = [
        {"start": f"{DAY}T09:00+02:00", "end": f"{DAY}T10:00+02:00"},
        {"start": f"{DAY}T09:30+02:00", "end": f"{DAY}T10:30+02:00"},
    ]
    clashes = find_clashes(agenda)
    assert (clashes[0].a, clashes[0].b) == ("item-0", "item-1")


# ── validation ───────────────────────────────────────────────────────────────


def test_end_before_start_raises_with_slot_id():
    with pytest.raises(ValueError, match="'broken'"):
        find_clashes([slot("broken", "10:00", "09:00")])


def test_zero_length_slot_raises():
    with pytest.raises(ValueError):
        find_clashes([slot("zero", "10:00", "10:00")])


def test_missing_time_raises_with_slot_id():
    with pytest.raises(ValueError, match="'nostart'"):
        find_clashes([{"id": "nostart", "end": f"{DAY}T10:00+02:00"}])


def test_non_mapping_item_raises():
    with pytest.raises(ValueError):
        find_clashes(["not a slot"])  # type: ignore[list-item]


# ── sweep vs brute force ────────────────────────────────────────────────────


def _brute_force(slots: list[Slot]) -> set[tuple[str, str]]:
    pairs = set()
    for a, b in combinations(slots, 2):
        if a.start < b.end and b.start < a.end:
            pairs.add(tuple(sorted((a.id, b.id))))
    return pairs


@pytest.mark.parametrize("seed", range(25))
def test_sweep_matches_brute_force(seed):
    rng = random.Random(seed)
    base = parse_dt(f"{DAY}T08:00+02:00")
    slots = []
    for i in range(rng.randint(0, 14)):
        start = base + timedelta(minutes=15 * rng.randint(0, 36))
        end = start + timedelta(minutes=15 * rng.randint(1, 8))
        slots.append(Slot(f"s{i}", start, end))
    expected = _brute_force(slots)
    got = {tuple(sorted((c.a, c.b))) for c in find_clashes(slots)}
    assert got == expected
    assert clash_count(slots) == len(expected)
