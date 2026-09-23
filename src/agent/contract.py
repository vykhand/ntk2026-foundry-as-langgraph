"""The agenda output contract.

The agent's final message carries two things (scenario spec §Agent design):

1. a fenced ```json block — ``{"day": ..., "attendee": ..., "items": [...]}``
   where each item is ``{"id", "title", "room", "start", "end"}`` — this is
   what the evals score;
2. a short Slovene narrative for the human.

This module extracts (1) from arbitrary assistant text and resolves item ids
against the program so that evals use authoritative times even if the model
mistyped one.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Mapping
from typing import Any

# A plain pattern string, deliberately not pre-built with the re module's builder function:
# this module is embedded verbatim in the Foundry code-based evaluators, and the Python-grader
# sandbox rejects the source if that builtin's name appears anywhere in it (the talk's write-up, D-20).
_FENCE_PATTERN = r"```(?:json|JSON)?\s*\n(.*?)```"
_DECODER = json.JSONDecoder()


def _candidate_objects(text: str):
    """Yield JSON objects found in fenced blocks first, then bare objects."""
    for block in re.findall(_FENCE_PATTERN, text, re.DOTALL):
        try:
            yield json.loads(block)
        except json.JSONDecodeError:
            continue
    for match in re.finditer(r"\{", text):
        try:
            obj, _ = _DECODER.raw_decode(text, match.start())
        except json.JSONDecodeError:
            continue
        yield obj


def extract_agenda(text: str) -> dict[str, Any] | None:
    """Return the **last** JSON object in *text* that has an ``items`` list, else ``None``.

    Last, not first: when the guard node (``agent.guard``) sends an agenda back for repair, the
    turn's text carries the rejected agenda *and* the corrected one, in that order. Scoring the
    first block would grade the answer the agent already threw away — which is exactly what
    happened on 2026-09-06 before this changed (the talk's write-up, S-08b).
    """
    if not text:
        return None
    found = None
    for obj in _candidate_objects(text):
        if isinstance(obj, dict) and isinstance(obj.get("items"), list):
            found = obj
    return found


def resolve_items(
    agenda: Mapping[str, Any],
    lookup: Callable[[str], Mapping[str, Any] | None],
) -> dict[str, Any]:
    """Fill ``start``/``end``/``room``/``title`` from the program by ``id``.

    Program data wins over whatever the model wrote; ids the program does not
    know are kept as-is (with the model's times) and listed in ``unknown_ids``
    so the eval can penalise hallucinated talks separately from clashes.
    """
    items: list[dict[str, Any]] = []
    unknown: list[str] = []
    for raw in agenda.get("items", []):
        if not isinstance(raw, Mapping):
            continue
        item = dict(raw)
        talk_id = str(item.get("id") or "").strip()
        talk = lookup(talk_id) if talk_id else None
        if talk is None:
            if talk_id:
                unknown.append(talk_id)
        else:
            for key in ("title", "room", "start", "end", "speaker", "track"):
                if key in talk:
                    item[key] = talk[key]
        items.append(item)
    return {**agenda, "items": items, "unknown_ids": unknown}


__all__ = ["extract_agenda", "resolve_items"]
