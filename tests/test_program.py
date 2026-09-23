"""Fixture integrity + search behaviour over the real ntk.si programme (``uv run fetch-program``)."""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

import jsonschema
import pytest

from agent.clash_checker import find_clashes
from agent.preferences import get_persona, load_personas
from agent.program import Program, load_program, normalize_text

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def program() -> Program:
    return load_program()


def test_fixture_validates_against_schema(program):
    schema = json.loads((ROOT / "fixtures" / "program.schema.json").read_text(encoding="utf-8"))
    data = json.loads(program.path.read_text(encoding="utf-8"))
    jsonschema.validate(data, schema)


def test_ids_are_unique_and_sequential(program):
    ids = [t["id"] for t in program.talks]
    assert len(ids) == len(set(ids))
    assert ids == [f"t-{n:03d}" for n in range(1, len(ids) + 1)]


def test_exactly_one_synthetic_joke_target(program):
    joke = [t for t in program.talks if t["synthetic"]]
    assert len(joke) == 1
    assert joke[0]["title"] == "Digitalna transformacija digitalne transformacije 2.0"
    assert joke[0]["speaker"] == "dr. Sinergija Paradigma"


# Double bookings present in the ntk.si data itself — the fixture mirrors the site, it does not repair
# it. Tue Mediteranea 1 13:00 was one on 2026-09-13; ntk.si fixed it by 2026-09-16. Add, don't hide.
KNOWN_NTK_DOUBLE_BOOKINGS: set[tuple[str, str]] = set()


def test_no_room_is_double_booked_beyond_what_ntk_si_publishes(program):
    by_room = defaultdict(list)
    for talk in program.talks:
        by_room[(program.day_of(talk), talk["room"])].append(talk)
    for key, talks in by_room.items():
        if key in KNOWN_NTK_DOUBLE_BOOKINGS:
            continue
        assert find_clashes(talks) == [], f"room double-booked: {key}"


def test_the_joke_talk_takes_no_real_speakers_room(program):
    joke = next(t for t in program.talks if t["synthetic"])
    assert all(t["room"] != joke["room"] for t in program.talks if not t["synthetic"])


def test_all_talks_fall_on_conference_days(program):
    assert set(program.days) == {"2026-09-21", "2026-09-22", "2026-09-23"}
    for talk in program.talks:
        assert program.day_of(talk) in program.days
        assert talk["start"].endswith("+02:00") and talk["end"].endswith("+02:00")


def test_author_talks_are_present_for_cross_promotion(program):
    titles = {t["title"] for t in program.talks}
    assert "Bring Your Own Agent: LangGraph in Production on Foundry Agent Service" in titles


def test_tuesday_has_designed_ai_azure_clash_potential(program):
    """The rehearsal persona (AI + Azure, Tuesday) must face real overlaps to resolve."""
    tuesday = [t for t in program.talks if program.day_of(t) == "2026-09-22"]
    interesting = [t for t in tuesday if t["track"] in {"AI", "Azure"}]
    assert len(interesting) >= 15
    assert len(find_clashes(interesting)) >= 10


# ── search ──────────────────────────────────────────────────────────────────


def test_normalize_text_strips_diacritics():
    assert normalize_text("Čista Šola Žoga") == "cista sola zoga"


def test_search_is_diacritics_insensitive(program):
    with_diacritics = program.search("varnost DevOps cevovodov")
    without = program.search("varnost devops cevovodov")
    assert with_diacritics and with_diacritics[0]["id"] == without[0]["id"]


def test_search_day_aliases(program):
    torek = program.search(day="torek", limit=80)
    tuesday = program.search(day="tuesday", limit=80)
    iso = program.search(day="2026-09-22", limit=80)
    assert torek == tuesday == iso
    assert all(t["day"] == "torek" for t in torek)
    assert 30 <= len(torek) <= 80


def test_search_track_aliases(program):
    assert {t["track"] for t in program.search(track="security", limit=80)} == {"Varnost"}
    assert {t["track"] for t in program.search(track="AI", day="torek", limit=80)} == {"AI"}


def test_search_unknown_day_or_track_raises(program):
    with pytest.raises(ValueError):
        program.search(day="petek")
    with pytest.raises(ValueError):
        program.search(track="gastronomija")


def test_search_query_ranks_title_hits_first(program):
    results = program.search("passkeys")
    assert "Passkeys" in results[0]["title"]


def test_search_empty_query_with_no_filter_lists_up_to_the_cap(program):
    """125 real talks outgrow the 80-result cap; a single day (≤ 50) still lists in full."""
    assert len(program.search(limit=80)) == min(80, len(program.talks))
    assert len(program.search(day="torek", limit=80)) == sum(
        program.day_of(t) == "2026-09-22" for t in program.talks
    )


def test_search_limit_is_clamped(program):
    assert len(program.search(limit=1000)) == min(80, len(program.talks))
    assert len(program.search(limit=0)) == 1


def test_compact_marks_the_joke_talk(program):
    joke = next(t for t in program.talks if t["synthetic"])
    assert program.compact(joke)["synthetic"] is True
    assert "synthetic" not in program.compact(program.talks[0])


def test_slots_resolve_known_and_unknown_ids(program):
    found, unknown = program.slots(["t-001", "t-999", " t-002 "])
    assert [s["id"] for s in found] == ["t-001", "t-002"]
    assert unknown == ["t-999"]


# ── personas ────────────────────────────────────────────────────────────────


def test_personas_are_fictional_and_have_constraints():
    personas = load_personas()["attendees"]
    assert {p["id"] for p in personas} == {"maja", "tomaz", "nina"}
    for persona in personas:
        assert "constraints" in persona and "interests" in persona


def test_get_persona_by_id_or_name_and_default(monkeypatch):
    assert get_persona("maja")["constraints"]["earliest_start"] == "09:00"
    assert get_persona("Tomaž")["id"] == "tomaz"
    monkeypatch.setenv("NTK_ATTENDEE", "nina")
    assert get_persona()["id"] == "nina"
    with pytest.raises(KeyError):
        get_persona("nobody")
