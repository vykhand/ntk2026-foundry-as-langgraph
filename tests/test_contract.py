from __future__ import annotations

from agent.contract import extract_agenda, resolve_items

NARRATIVE = """Tukaj je tvoj urnik za torek:

```json
{"day": "2026-09-22", "attendee": "maja",
 "items": [{"id": "t-010", "title": "Agenti", "room": "Emerald",
            "start": "2026-09-22T09:00:00+02:00", "end": "2026-09-22T10:00:00+02:00"}]}
```

Ob 10:00 imaš pol ure za kavo. Lep dan!"""


def test_extracts_fenced_json_block():
    agenda = extract_agenda(NARRATIVE)
    assert agenda is not None
    assert agenda["day"] == "2026-09-22"
    assert agenda["items"][0]["id"] == "t-010"


def test_extracts_bare_json_object_without_fence():
    text = 'Urnik: {"items": [{"id": "t-001"}], "day": "2026-09-22"} — konec.'
    assert extract_agenda(text)["items"][0]["id"] == "t-001"


def test_ignores_json_without_items():
    text = '```json\n{"clash_count": 0}\n```\nNi urnika.'
    assert extract_agenda(text) is None


def test_skips_a_tool_echo_that_has_no_items():
    text = '```json\n{"clash_count": 0, "clashes": []}\n```\n```json\n{"items": [{"id": "t-002"}]}\n```'
    assert extract_agenda(text)["items"][0]["id"] == "t-002"


def test_takes_the_last_agenda_when_the_guard_asked_for_a_repair():
    """The rejected agenda comes first in the turn's text; the repaired one wins (S-08b)."""
    text = (
        '```json\n{"day": "2026-09-22", "items": [{"id": "t-062"}]}\n```\n'
        "Popravljam urnik.\n"
        '```json\n{"day": "2026-09-22", "items": [{"id": "t-018"}]}\n```'
    )
    assert extract_agenda(text)["items"][0]["id"] == "t-018"


def test_empty_or_broken_text_returns_none():
    assert extract_agenda("") is None
    assert extract_agenda("```json\n{not json\n```") is None


def test_resolve_items_overrides_with_program_data_and_flags_unknown_ids():
    program = {
        "t-010": {
            "id": "t-010",
            "title": "Pravi naslov",
            "room": "Emerald",
            "start": "2026-09-22T09:00:00+02:00",
            "end": "2026-09-22T10:00:00+02:00",
        },
    }
    agenda = {
        "items": [
            {"id": "t-010", "title": "Napačen naslov", "start": "2026-09-22T09:05:00+02:00"},
            {
                "id": "t-999",
                "title": "Izmišljeno",
                "start": "2026-09-22T11:00:00+02:00",
                "end": "2026-09-22T11:45:00+02:00",
            },
        ]
    }
    resolved = resolve_items(agenda, program.get)
    assert resolved["items"][0]["title"] == "Pravi naslov"
    assert resolved["items"][0]["start"] == "2026-09-22T09:00:00+02:00"
    assert resolved["items"][1]["title"] == "Izmišljeno"
    assert resolved["unknown_ids"] == ["t-999"]
