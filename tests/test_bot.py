"""The Telegram formatter, which is the only logic the bot has.

Its one real hazard: the deployed graph re-checks its own answer, and the hosting layer puts every
node's message on the wire (the talk's write-up, S-08e), so a corrected turn arrives with the rejected draft
*and* the repair. Rendering both would hand someone a phone full of talks the agent discarded.
"""

from __future__ import annotations

from scripts.telegram_bot import SORRY, _format

ONE = """```json
{"day": "2026-09-22", "attendee": "nina", "items": [
 {"id": "t-018", "title": "Lakehouse vzorci", "room": "Mediteranea",
  "start": "2026-09-22T09:00:00+02:00", "end": "2026-09-22T09:45:00+02:00"}]}
```

Sestavil sem ti torek."""

CORRECTED = """```json
{"day": "2026-09-22", "items": [
 {"id": "t-050", "title": "Prepozno predavanje", "room": "Mediteranea",
  "start": "2026-09-22T15:00:00+02:00", "end": "2026-09-22T15:45:00+02:00"}]}
```

Osnutek, ki ga je preverba zavrnila.
```json
{"day": "2026-09-22", "items": [
 {"id": "t-018", "title": "Popravljeno predavanje", "room": "Mediteranea",
  "start": "2026-09-22T09:00:00+02:00", "end": "2026-09-22T09:45:00+02:00"}]}
```

Popravljen urnik, ki se konča pred tvojim odhodom."""


def test_a_plain_answer_becomes_a_list_and_a_sentence():
    out = _format(ONE)
    assert "09:00–09:45" in out
    assert "Lakehouse vzorci" in out
    assert "Mediteranea" in out
    assert "Sestavil sem ti torek." in out
    assert "```" not in out and "json" not in out


def test_only_the_repaired_agenda_reaches_the_phone():
    out = _format(CORRECTED)
    assert "Popravljeno predavanje" in out
    assert "Prepozno predavanje" not in out, "the rejected draft must not be rendered"
    assert "15:00–15:45" not in out
    assert "Popravljen urnik" in out
    assert "Osnutek" not in out, "the draft's narration explains a schedule nobody sees"


def test_an_answer_with_no_agenda_still_says_something():
    assert _format("Za kateri dan naj sestavim urnik?") == "Za kateri dan naj sestavim urnik?"
    assert _format("") == "…"


def test_broken_json_does_not_take_the_bot_down():
    out = _format("```json\n{not json\n```\n\nNekaj je šlo narobe.")
    assert "Nekaj je šlo narobe." in out


def test_the_message_is_capped_for_telegram():
    assert len(_format("x" * 9000)) <= 4096


def test_a_failure_message_carries_nothing_from_the_error():
    """An auth failure names the signed-in Azure account; the chat is on the projector."""
    assert "@" not in SORRY and "Error" not in SORRY
