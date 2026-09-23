"""The guard node's checker (the talk's write-up, S-08b).

The guard exists because prompting could not enforce ``latest_end`` measurably (six 22-row runs,
2026-09-06). These tests pin the behaviour the eval delta depends on: a violating agenda must be
caught, a clean one must pass untouched, and the complaint must name the offending talk.
"""

from __future__ import annotations

import json
from pathlib import Path

from agent import guard
from agent.program import load_program

GOLDEN = Path(__file__).resolve().parents[1] / "evals" / "golden.jsonl"


def _agenda(attendee: str, day: str, ids: list[str]) -> str:
    program = load_program()
    items = []
    for talk_id in ids:
        talk = program.get(talk_id)
        assert talk is not None, talk_id
        items.append(
            {
                "id": talk["id"],
                "title": talk["title"],
                "room": talk["room"],
                "start": talk["start"],
                "end": talk["end"],
            }
        )
    payload = {"day": day, "attendee": attendee, "items": items}
    return "```json\n" + json.dumps(payload, ensure_ascii=False) + "\n```\n\nKratka razlaga."


def _tuesday(track: str) -> list[dict]:
    return sorted(
        (t for t in load_program().talks if t["start"].startswith("2026-09-22") and t["track"] == track),
        key=lambda t: t["start"],
    )


def _late_tuesday() -> dict:
    """A Tuesday talk ending after Tomaž's 16:00, whatever its track — ntk.si moves talks around."""
    return next(
        t for t in load_program().talks if t["start"].startswith("2026-09-22") and t["end"][11:16] > "16:00"
    )


def test_clean_agenda_passes():
    # The real programme runs parallel security talks, so pick a day that could actually be sat through.
    early, free_from = [], ""
    for talk in _tuesday("Varnost"):
        if talk["end"][11:16] <= "16:00" and talk["start"] >= free_from and len(early) < 3:
            early.append(talk["id"])
            free_from = talk["end"]
    assert guard.violations_of(_agenda("tomaz", "2026-09-22", early)) == []


def test_talk_past_latest_end_is_caught_and_named():
    talks = _tuesday("Varnost")
    late = _late_tuesday()
    problems = guard.violations_of(_agenda("tomaz", "2026-09-22", [talks[0]["id"], late["id"]]))
    assert problems, "a talk ending after 16:00 must be reported for tomaz"
    assert any(late["id"] in p and "16:00" in p for p in problems)


def test_maja_has_no_latest_end_so_a_late_talk_is_fine():
    talks = _tuesday("AI")
    late = next(t for t in talks if t["end"][11:16] > "16:00")
    assert guard.violations_of(_agenda("maja", "2026-09-22", [late["id"]])) == []


def test_overlapping_talks_are_caught():
    talks = _tuesday("AI")
    pair = None
    for i, a in enumerate(talks):
        for b in talks[i + 1 :]:
            if b["start"] < a["end"] and b["end"] <= "2026-09-22T16:00:00+02:00":
                pair = (a["id"], b["id"])
                break
        if pair:
            break
    assert pair, "the Tuesday AI track is supposed to overlap itself"
    problems = guard.violations_of(_agenda("maja", "2026-09-22", list(pair)))
    assert any("prekrivajo" in p for p in problems)


def test_unknown_id_is_reported():
    text = (
        '```json\n{"day": "2026-09-22", "attendee": "maja", '
        '"items": [{"id": "t-999", "title": "X", "room": "Y", '
        '"start": "2026-09-22T09:00:00+02:00", "end": "2026-09-22T09:45:00+02:00"}]}\n```'
    )
    assert any("t-999" in p for p in guard.violations_of(text))


def test_answer_without_an_agenda_is_not_second_guessed():
    assert guard.violations_of("Zdravo! Za kateri dan naj sestavim urnik?") == []


def _tool_message(persona_id: str):
    """What the ``preferences`` tool puts back into the conversation."""
    from langchain_core.messages import ToolMessage

    from agent.preferences import get_persona

    return ToolMessage(
        content=json.dumps(get_persona(persona_id), ensure_ascii=False),
        name=guard.PROFILE_TOOL,
        tool_call_id="call-1",
    )


def test_attendee_comes_from_the_profile_tool_not_the_models_json():
    """The model dropping ``attendee`` must not downgrade the guard to the default persona."""
    late = _late_tuesday()
    text = _agenda("tomaz", "2026-09-22", [late["id"]]).replace('"attendee": "tomaz", ', "")
    assert "attendee" not in text

    assert guard.violations_of(text) == []  # no tool result: falls back to maja, sees nothing
    verdict = guard.inspect(text, messages=[_tool_message("tomaz")])
    assert verdict["attendee"] == "tomaz"
    assert verdict["attendee_source"] == "tool"
    assert any(late["id"] in p for p in verdict["problems"])


def test_the_tool_result_wins_over_a_contradicting_agenda_field():
    late = _late_tuesday()
    text = _agenda("maja", "2026-09-22", [late["id"]])  # model claims maja; the tool says tomaz
    verdict = guard.inspect(text, messages=[_tool_message("tomaz")])
    assert verdict["attendee"] == "tomaz"
    assert verdict["enforced"]["latest_end"] == "16:00"
    assert verdict["problems"]


def test_attendee_from_messages_ignores_other_tools_and_bad_json():
    from langchain_core.messages import ToolMessage

    assert guard.attendee_from_messages([]) is None
    other = ToolMessage(content='{"id": "t-001"}', name="program_search", tool_call_id="c")
    assert guard.attendee_from_messages([other]) is None
    broken = ToolMessage(content="not json", name=guard.PROFILE_TOOL, tool_call_id="c")
    assert guard.attendee_from_messages([broken]) is None
    assert guard.attendee_from_messages([other, _tool_message("nina")]) == "nina"


def test_requested_attendee_reads_the_name_out_of_the_question():
    assert guard.requested_attendee("Nina tukaj — v torek bi šla na podatke.") == "nina"
    assert guard.requested_attendee("Tomaž tukaj. Sestavi mi urnik za torek.") == "tomaz"
    assert guard.requested_attendee("Za torek bi rada AI predavanja.") is None
    # Two people named: decline rather than pick one.
    assert guard.requested_attendee("Maja in Nina greva skupaj.") is None


def test_the_question_outranks_a_wrong_profile_lookup():
    """Row g19 on deployed v4: "Nina tukaj", but the model looked up the default persona (S-08e).

    Nina leaves at 15:00 and Maja has no ``latest_end``, so grading Nina's day as Maja's is a
    guard that approves anything.
    """
    talks = _tuesday("Podatki") or _tuesday("AI")
    late = next(t for t in talks if t["end"][11:16] > "15:00")
    text = _agenda("maja", "2026-09-22", [late["id"]])  # model built Maja's day
    question = "Nina tukaj — v torek bi šla na podatke in Fabric."

    assert guard.inspect(text, messages=[_tool_message("maja")])["problems"] == []
    verdict = guard.inspect(text, messages=[_tool_message("maja")], question=question)
    assert verdict["attendee"] == "nina"
    assert verdict["attendee_source"] == "question"
    assert verdict["enforced"]["latest_end"] == "15:00"
    assert any(late["id"] in p for p in verdict["problems"])


def test_requested_day_reads_inflected_slovene_weekdays():
    program = load_program()
    assert guard.requested_day("Nina tukaj — v torek bi šla na podatke.", program) == "2026-09-22"
    assert guard.requested_day("Kaj je zame zanimivega v sredo?", program) == "2026-09-23"
    assert guard.requested_day("Sestavi mi urnik za ponedeljek.", program) == "2026-09-21"
    assert guard.requested_day("Za 2026-09-22 prosim.", program) == "2026-09-22"
    assert guard.requested_day("Kaj naj poslušam?", program) is None
    # A bare number is a time, not a date: "ob 22" must not book the whole of Tuesday.
    assert guard.requested_day("Grem domov ob 22 uri.", program) is None
    # Two days named: no rule picks the right one, so the guard declines to guess.
    assert guard.requested_day("V ponedeljek ne morem, sestavi mi torek.", program) is None


def test_every_golden_question_resolves_to_its_own_day():
    """The day check is only worth having if it reads all 22 rows the way the rows intend."""
    program = load_program()
    rows = [
        json.loads(line)
        for line in GOLDEN.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    mismatched = [
        (r["id"], r["day"], guard.requested_day(r["query"], program))
        for r in rows
        if guard.requested_day(r["query"], program) != r["day"]
    ]
    assert mismatched == []


def test_an_agenda_on_the_wrong_day_is_caught_even_when_it_says_so_itself():
    """Row g22, 2026-09-06: "v torek" answered with a Wednesday agenda (S-08c).

    The guard used to take the requested day from the agenda, so the answer's own claim decided
    whether the answer was on the right day — and it always was.
    """
    wednesday: list[str] = []
    last_end = ""
    for talk in sorted(load_program().talks, key=lambda t: t["start"]):
        if not talk["start"].startswith("2026-09-23") or talk["end"][11:16] > "15:00":
            continue
        if talk["start"] >= last_end:  # keep the fixture agenda clash-free
            wednesday.append(talk["id"])
            last_end = talk["end"]
    text = _agenda("nina", "2026-09-23", wednesday[:2])

    assert guard.violations_of(text) == []  # no question: the agenda grades itself, as before
    verdict = guard.inspect(text, question="Nina tukaj — v torek bi šla na podatke in Fabric.")
    assert verdict["day"] == "2026-09-22"
    assert verdict["day_source"] == "question"
    assert any("niso na zahtevanem dnevu" in p for p in verdict["problems"])


def test_the_day_falls_back_to_the_agenda_when_the_question_names_none():
    talks = _tuesday("Varnost")
    text = _agenda("tomaz", "2026-09-22", [talks[0]["id"]])
    verdict = guard.inspect(text, question="Sestavi mi urnik, prosim.")
    assert verdict["day"] == "2026-09-22"
    assert verdict["day_source"] == "agenda"
    assert verdict["problems"] == []


def test_verdict_logs_as_one_parseable_json_line():
    talks = _tuesday("Varnost")
    verdict = guard.inspect(_agenda("tomaz", "2026-09-22", [talks[0]["id"]]))
    line = guard.format_verdict(verdict, decision="pass", q="Tomaž tukaj.", attempt=1)
    assert line.startswith("[guard] ")
    payload = json.loads(line[len("[guard] ") :])
    assert payload["decision"] == "pass"
    assert payload["attendee_source"] == "agenda"
    assert payload["enforced"]["latest_end"] == "16:00"


def test_asked_returns_the_original_question_not_the_correction():
    from langchain_core.messages import AIMessage, HumanMessage

    messages = [
        HumanMessage(content="Nina tukaj — v torek bi šla na podatke."),
        AIMessage(content="urnik"),
        HumanMessage(content=guard.correction_message(["nekaj je narobe"])),
    ]
    assert guard.asked(messages) == "Nina tukaj — v torek bi šla na podatke."


def test_text_of_flattens_responses_v1_content_blocks():
    class _M:
        content = [{"type": "text", "text": "prvi"}, {"type": "text", "text": " drugi"}]

    assert guard.text_of(_M()) == "prvi drugi"


def test_correction_message_is_marked_and_countable():
    message = guard.correction_message(["nekaj je narobe"])
    assert guard.CORRECTION_MARKER in message

    class _M:
        def __init__(self, content: str) -> None:
            self.content = content

    assert guard.corrections_so_far([_M("navaden odgovor")]) == 0
    assert guard.corrections_so_far([_M(message), _M("odgovor"), _M(message)]) == 2
