"""Deterministic post-check of the agent's own answer (the talk's write-up, S-08b).

Measured 2026-09-06: telling the model to respect the attendee's ``latest_end`` does not work.
Across six 22-row runs the model reads the profile, sees "I go home at four", and then schedules
past it anyway whenever the request pushes for volume ("cel dan", "čim več predavanj") — and the
difference between prompt variants was smaller than the difference between two runs of the *same*
prompt, so no amount of prompt wording is measurably fixing it.

So the check does not live in the prompt. It lives in the graph: parse the agenda the model just
wrote, score it with the same functions the evals use, and hand the specific violations back for
one more attempt. Plain Python over the model's output — no Foundry, no extra model call.

**Nothing the guard checks against may come out of the model's own choices.** Learned three times
in one day (S-08b, S-08c, S-08e), each time in a new costume: the guard graded the rejected draft
instead of the repair; it took the requested day from the agenda's own ``day`` field, so
``off_day`` was true by construction; and it took *who* from the ``preferences`` tool result,
which is only the model's lookup — on g19 the model asked for no one in particular, got the
default persona, and the guard dutifully enforced the wrong person's constraints.

So both directions come from the **question**, the one text in the conversation the model did not
write: ``requested_attendee`` and ``requested_day``. The tool result and the agenda's own fields
survive only as fallbacks. The answer supplies the thing under test and nothing else.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from typing import Any

from agent.clash_checker import clash_report, normalize
from agent.contract import extract_agenda, resolve_items
from agent.metrics import Preferences, evaluate_agenda
from agent.preferences import default_attendee, get_persona, load_personas
from agent.program import Program, load_program, normalize_text

# Marker on the correction message, so the graph can tell "I already tried" from a fresh turn
# without adding a channel to MessagesState.
CORRECTION_MARKER = "[NTK_GUARD]"
MAX_CORRECTIONS = 2

# The tool whose result tells the guard *whose* constraints to enforce.
PROFILE_TOOL = "preferences"


def _hhmm(value: str) -> str:
    """'2026-09-22T16:45:00+02:00' → '16:45'."""
    return value[11:16] if len(value) >= 16 else value


def attendee_from_messages(messages: Sequence[Any]) -> str | None:
    """The persona the ``preferences`` tool actually returned this turn, if it was called.

    The agenda's own ``attendee`` field is only the model's word for it, and the model drops that
    field often enough to matter: with no attendee the guard falls back to the default persona
    and grades Nina's day against Maja's constraints — Maja has no ``latest_end``, so a talk
    running to 17:45 sails straight through a guard that was supposed to catch it. The tool result
    is the one signal the model cannot get wrong by omission: it *is* the profile it was shown.
    """
    for message in reversed(list(messages)):
        if getattr(message, "type", "") != "tool" or getattr(message, "name", "") != PROFILE_TOOL:
            continue
        content = getattr(message, "content", "")
        if not isinstance(content, str):
            return None
        try:
            payload = json.loads(content)
        except json.JSONDecodeError:
            return None
        who = payload.get("id") if isinstance(payload, Mapping) else None
        return str(who) if who else None
    return None


# Slovene weekdays as they appear inside a sentence: "v torek", "za sredo", "v ponedeljek".
# ``Program.resolve_day`` only matches a whole value, which is right for a tool argument and
# useless for prose, so the inflected forms are spelled out rather than stemmed — three
# conference days do not justify a morphology engine, and a wrong stem would silently mis-day
# the whole check.
_DAY_WORDS: dict[str, tuple[str, ...]] = {
    "ponedeljek": ("ponedeljek", "ponedeljka", "ponedeljku", "ponedeljkom", "monday"),
    "torek": ("torek", "torka", "torku", "torkom", "tuesday"),
    "sreda": ("sreda", "sredo", "srede", "sredi", "wednesday"),
    "cetrtek": ("cetrtek", "cetrtka", "cetrtku", "cetrtkom", "thursday"),
    "petek": ("petek", "petka", "petku", "petkom", "friday"),
}


def requested_day(question: str, program: Program) -> str | None:
    """The conference day *question* asks for, or ``None`` when it names none.

    Why this exists: the guard used to take the day from the agenda it was checking, so
    ``off_day`` could never fire — the answer was graded against its own claim. On 2026-09-06 the
    model answered "v torek" with a Wednesday agenda (Nina's profile says she attends Wednesday),
    the guard agreed with it, and the eval counted two violations the guard had just waved
    through (S-08c, row g22). A check that reads its expectations out of the thing it is checking
    is not a check.
    """
    tokens = re.findall(r"[\w.\-]+", normalize_text(question))
    words = {token.strip(".") for token in tokens}  # "torek." at the end of a sentence
    named = [
        day
        for day, label in program.day_labels().items()
        if words & set(_DAY_WORDS.get(normalize_text(label), ()))
    ]
    for token in tokens:
        # "2026-09-22" and "22.9." only. A bare "22" is a time ("grem ob 22"), and taking it for
        # a date would silently re-day the whole check on the strength of a clock reading.
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}|\d{1,2}\.\d{1,2}\.?", token):
            continue
        try:
            named.append(program.resolve_day(token))
        except ValueError:
            continue
    # Exactly one, or none: "v ponedeljek ne morem, sestavi mi torek" names two days and no
    # deterministic rule picks the right one. Guessing there would reject a *correct* agenda,
    # which is worse than missing a violation, so an ambiguous question falls back to the
    # agenda's own day — the old, weaker behaviour, and only for the rows that earn it.
    return named[0] if len(set(named)) == 1 else None


def requested_attendee(question: str) -> str | None:
    """The persona *question* names, or ``None``. Beats the tool result — see why below.

    The ``preferences`` tool result was supposed to be the unfakeable signal for *who*, and it is
    not: on row g19 ("Nina tukaj — v sredo…") the deployed v4 agent called ``preferences()`` with
    no argument, got the default persona back, and built Maja's day. The tool agreed with the
    agenda, both were wrong, and the guard enforced Maja's constraints — which is to say none.
    The question is the only place the requester's identity is not the model's own choice.
    """
    names = {}
    for persona in load_personas()["attendees"]:
        for alias in (persona["id"], persona.get("name", "")):
            if alias:
                names[normalize_text(alias)] = persona["id"]
    words = {token.strip(".,!?") for token in re.findall(r"[\w.,!?\-]+", normalize_text(question))}
    found = {names[word] for word in words if word in names}
    return next(iter(found)) if len(found) == 1 else None


def inspect(
    text: str,
    *,
    attendee: str | None = None,
    messages: Sequence[Any] | None = None,
    question: str = "",
) -> dict[str, Any]:
    """Everything the guard concluded about *text* — the verdict behind :func:`violations_of`.

    Returned as a dict rather than just the complaints so the graph can log *why* the guard
    passed an answer. A guard that silently approves is indistinguishable from a guard that is
    not running, which is precisely how the residual failures in S-08b stayed unexplained.
    """
    agenda = extract_agenda(text)
    if agenda is None:
        return {"agenda": False, "problems": []}

    program = load_program()
    resolved = resolve_items(agenda, program.get)
    items = resolved["items"]

    from_question = requested_attendee(question) if question else None
    from_tool = attendee_from_messages(messages or [])
    if from_question:
        who, source = from_question, "question"
    elif from_tool:
        who, source = from_tool, "tool"
    elif agenda.get("attendee"):
        who, source = str(agenda["attendee"]), "agenda"
    elif attendee:
        who, source = attendee, "caller"
    else:
        who, source = default_attendee(), "default"

    try:
        persona = get_persona(who)
    except KeyError:
        persona = {}
    prefs = Preferences.from_persona(persona) if persona else Preferences()

    asked_for = requested_day(question, program) if question else None
    day = asked_for or agenda.get("day")
    report = evaluate_agenda(items, prefs, day=day)
    pv = report["preference_violations"]
    slots = {s.id: s for s in normalize(items)}
    problems: list[str] = []

    if resolved["unknown_ids"]:
        problems.append(
            f"Ti `id`-ji niso v programu: {', '.join(resolved['unknown_ids'])}. "
            "Uporabi samo predavanja, ki jih vrne `program_search`."
        )
    if report["clash_count"]:
        pairs = ", ".join(
            f"{c['a']}+{c['b']}" for c in clash_report(normalize(items))["clashes"][:4]
        )
        problems.append(f"Predavanja se prekrivajo ({pairs}). Eno od vsakega para odstrani.")
    for talk_id in pv["after_latest"]:
        end = _hhmm(str(slots[talk_id].end)) if talk_id in slots else "?"
        problems.append(
            f"`{talk_id}` se konča ob {end}, udeleženec pa odide ob {pv['latest_end']}. Odstrani ga."
        )
    for talk_id in pv["before_earliest"]:
        start = _hhmm(str(slots[talk_id].start)) if talk_id in slots else "?"
        problems.append(
            f"`{talk_id}` se začne ob {start}, pred {pv['earliest_start']}. Odstrani ga."
        )
    if pv["off_day"]:
        problems.append(
            f"Ta predavanja niso na zahtevanem dnevu ({pv['requested_day']}): {', '.join(pv['off_day'])}."
        )
    if pv["missing_break"]:
        problems.append(
            f"Med 10:00 in 14:00 ni {pv['min_break_minutes']}-minutne luknje za kavo. "
            "Izpusti eno predavanje in jo naredi."
        )
    return {
        "agenda": True,
        "attendee": who,
        "attendee_source": source,
        # What the model wrote in the JSON, kept alongside what the tool said: when these two
        # disagree the log shows the exact turn where trusting the model would have graded the
        # answer against the wrong person's constraints.
        "claimed": agenda.get("attendee"),
        "known_persona": bool(persona),
        "day": day,
        "day_source": "question" if asked_for else ("agenda" if agenda.get("day") else None),
        "items": report["items"],
        "enforced": {
            "earliest_start": pv["earliest_start"],
            "latest_end": pv["latest_end"],
            "min_break_minutes": pv["min_break_minutes"],
        },
        "problems": problems,
    }


def violations_of(text: str, *, attendee: str | None = None) -> list[str]:
    """Human-readable Slovene complaints about the agenda in *text* (empty when it is fine)."""
    return inspect(text, attendee=attendee)["problems"]


def correction_message(problems: list[str]) -> str:
    """The text handed back to the model — specific, imperative, and marked as ours."""
    bullets = "\n".join(f"- {p}" for p in problems)
    return (
        f"{CORRECTION_MARKER} Preverba urnika je našla napake:\n{bullets}\n\n"
        "Popravi urnik in odgovori znova v isti obliki (blok ```json in kratka razlaga). "
        "Ne razlagaj popravkov, samo vrni popravljen urnik."
    )


def corrections_so_far(messages: list[Any]) -> int:
    """How many times this turn has already been sent back."""
    return sum(
        1
        for m in messages
        if isinstance(getattr(m, "content", None), str) and CORRECTION_MARKER in m.content
    )


def text_of(message: Any) -> str:
    """The plain text of a message, flattening the ``responses/v1`` list-of-blocks form."""
    content = getattr(message, "content", "")
    if isinstance(content, str):
        return content
    if isinstance(content, Sequence):
        return "".join(block.get("text", "") for block in content if isinstance(block, Mapping))
    return ""


def inspect_state(state: Mapping[str, Any]) -> dict[str, Any]:
    """The guard's verdict on the last message of *state* (convenience for the graph node)."""
    messages = list(state.get("messages") or [])
    if not messages:
        return {"agenda": False, "problems": []}
    return inspect(text_of(messages[-1]), messages=messages, question=asked(messages))


def check(state: Mapping[str, Any]) -> list[str]:
    """Violations in the last message of *state*."""
    return inspect_state(state)["problems"]


def asked(messages: Sequence[Any]) -> str:
    """The question that opened this turn — the log's handle on *which* row went wrong."""
    for message in messages:
        text = text_of(message)
        if getattr(message, "type", "") == "human" and CORRECTION_MARKER not in text:
            return text.strip()
    return ""


def format_verdict(verdict: Mapping[str, Any], *, decision: str, **extra: Any) -> str:
    """One JSON line per guard decision — greppable in the console and in App Insights.

    JSON rather than prose because these lines are meant to be joined against the eval results
    afterwards; ``decision`` and ``attendee_source`` are the two fields that explain a residual.
    """
    payload = {"decision": decision, **extra, **{k: v for k, v in verdict.items() if k != "agenda"}}
    return "[guard] " + json.dumps(payload, ensure_ascii=False, default=str)


__all__ = [
    "CORRECTION_MARKER",
    "MAX_CORRECTIONS",
    "PROFILE_TOOL",
    "asked",
    "attendee_from_messages",
    "check",
    "correction_message",
    "corrections_so_far",
    "format_verdict",
    "inspect",
    "inspect_state",
    "requested_attendee",
    "requested_day",
    "text_of",
    "violations_of",
]
