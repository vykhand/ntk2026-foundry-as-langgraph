from __future__ import annotations

from datetime import date

from agent.metrics import (
    Preferences,
    break_coverage,
    evaluate_agenda,
    free_intervals,
    preference_violations,
)

DAY = "2026-09-22"


def slot(id_: str, start: str, end: str, day: str = DAY) -> dict:
    return {"id": id_, "start": f"{day}T{start}:00+02:00", "end": f"{day}T{end}:00+02:00"}


# ── break coverage ──────────────────────────────────────────────────────────


def test_back_to_back_morning_has_no_coffee_gap():
    agenda = [slot("a", "10:00", "11:00"), slot("b", "11:00", "12:00"), slot("c", "12:00", "14:00")]
    result = break_coverage(agenda)
    assert result["ok"] is False
    assert result["longest_gap_minutes"] == 0
    assert result["talks_in_window"] == 3


def test_thirty_minute_gap_counts_exactly():
    agenda = [slot("a", "10:00", "11:00"), slot("b", "11:30", "14:00")]
    result = break_coverage(agenda)
    assert result["ok"] is True and result["longest_gap_minutes"] == 30


def test_twenty_nine_minute_gap_does_not_count():
    agenda = [slot("a", "10:00", "11:00"), slot("b", "11:29", "14:00")]
    assert break_coverage(agenda)["ok"] is False


def test_gap_before_first_talk_in_window_counts():
    agenda = [slot("a", "09:00", "09:45"), slot("b", "10:45", "14:00")]
    result = break_coverage(agenda)
    assert result["ok"] is True
    assert result["gaps"][0]["minutes"] == 45  # 10:00–10:45


def test_gap_after_last_talk_in_window_counts():
    agenda = [slot("a", "10:00", "13:15")]
    result = break_coverage(agenda)
    assert result["ok"] is True and result["longest_gap_minutes"] == 45


def test_talk_spanning_the_window_edge_is_clipped():
    agenda = [slot("a", "09:30", "10:20"), slot("b", "10:40", "14:30")]
    gaps = free_intervals(agenda)
    assert [(a.strftime("%H:%M"), b.strftime("%H:%M")) for a, b in gaps] == [("10:20", "10:40")]


def test_overlapping_talks_do_not_create_phantom_gaps():
    agenda = [slot("a", "10:00", "12:00"), slot("b", "11:00", "13:00"), slot("c", "13:00", "14:00")]
    assert break_coverage(agenda)["ok"] is False


def test_empty_agenda_is_trivially_covered_but_flagged():
    result = break_coverage([])
    assert result["ok"] is False  # nothing scheduled → no day → no gap information
    assert result["day"] is None


def test_day_is_taken_from_first_slot_when_not_given():
    agenda = [slot("w", "10:00", "13:45", day="2026-09-23")]
    result = break_coverage(agenda)
    assert result["day"] == "2026-09-23" and result["ok"] is False


def test_explicit_day_selects_the_right_day_of_a_multi_day_agenda():
    agenda = [slot("t", "10:00", "13:45"), slot("w", "10:00", "11:00", day="2026-09-23")]
    assert break_coverage(agenda, day=date(2026, 9, 22))["ok"] is False
    assert break_coverage(agenda, day=date(2026, 9, 23))["ok"] is True


# ── preference violations ───────────────────────────────────────────────────


def test_nothing_before_nine_is_enforced():
    prefs = Preferences.from_persona({"constraints": {"earliest_start": "09:00"}})
    agenda = [slot("early", "08:30", "09:15"), slot("fine", "09:00", "09:45")]
    result = preference_violations(agenda, prefs)
    assert result["before_earliest"] == ["early"]
    assert result["count"] == 1 and result["ok"] is False


def test_latest_end_is_enforced():
    prefs = Preferences(latest_end=__import__("datetime").time(15, 0))
    agenda = [slot("ok", "14:00", "15:00"), slot("late", "15:00", "15:45")]
    assert preference_violations(agenda, prefs)["after_latest"] == ["late"]


def test_requested_coffee_gap_missing_is_one_violation():
    prefs = {"earliest_start": "09:00", "min_break_minutes": 30}
    agenda = [slot("a", "10:00", "11:00"), slot("b", "11:00", "12:00"), slot("c", "12:00", "14:00")]
    result = preference_violations(agenda, prefs)
    assert result["missing_break"] is True and result["count"] == 1


def test_no_coffee_request_means_no_break_violation():
    agenda = [slot("a", "10:00", "11:00"), slot("b", "11:00", "12:00"), slot("c", "12:00", "14:00")]
    assert preference_violations(agenda, Preferences())["count"] == 0


def test_persona_without_constraints_parses_to_empty_preferences():
    assert Preferences.from_persona({"id": "x"}) == Preferences()


def test_talks_on_another_day_than_requested_are_violations():
    agenda = [slot("mon", "10:00", "10:45", day="2026-09-21"), slot("tue", "10:00", "10:45")]
    result = preference_violations(agenda, Preferences(), day="2026-09-22")
    assert result["off_day"] == ["mon"] and result["requested_day"] == "2026-09-22"
    assert result["count"] == 1 and result["ok"] is False


def test_without_a_requested_day_any_day_is_fine():
    agenda = [slot("mon", "10:00", "10:45", day="2026-09-21"), slot("tue", "10:00", "10:45")]
    result = preference_violations(agenda, Preferences())
    assert result["off_day"] == [] and result["requested_day"] is None and result["ok"] is True


def test_multi_day_agenda_is_not_trivially_clash_free_when_a_day_is_requested():
    """A 1.7B model once answered 'torek' with talks spread over three days; the eval must catch it."""
    persona = {"constraints": {"earliest_start": "09:00", "min_break_minutes": 30}}
    agenda = [
        slot("a", "09:00", "09:45", day="2026-09-21"),
        slot("b", "10:00", "10:45", day="2026-09-22"),
        slot("c", "11:00", "11:45", day="2026-09-23"),
    ]
    result = evaluate_agenda(agenda, persona, day="2026-09-22")
    assert result["clash_count"] == 0
    assert result["preference_violations"]["off_day"] == ["a", "c"]
    assert result["break_coverage"]["day"] == "2026-09-22"
    assert result["ok"] is False


# ── combined ────────────────────────────────────────────────────────────────


def test_evaluate_agenda_rolls_everything_up():
    persona = {"constraints": {"earliest_start": "09:00", "min_break_minutes": 30}}
    bad = [slot("a", "08:30", "09:30"), slot("b", "09:15", "10:15"), slot("c", "10:15", "14:00")]
    result = evaluate_agenda(bad, persona)
    assert result["clash_count"] == 1
    assert result["preference_violations"]["count"] == 2  # before nine + no coffee gap
    assert result["break_coverage"]["ok"] is False
    assert result["ok"] is False

    good = [slot("a", "09:00", "09:45"), slot("b", "10:00", "10:45"), slot("c", "11:30", "12:15")]
    result = evaluate_agenda(good, persona)
    assert result["ok"] is True and result["clash_count"] == 0
