"""Conference program access: loading, lookup and keyword search over the fixture.

The running agent only ever reads ``fixtures/program.json`` (scenario spec §Data
plan 2); scraping/refreshing happens at build time in ``scripts/``.
"""

from __future__ import annotations

import json
import os
import unicodedata
from collections.abc import Iterable
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PROGRAM_PATH = ROOT / "fixtures" / "program.json"

WEEKDAYS_SL = ("ponedeljek", "torek", "sreda", "četrtek", "petek", "sobota", "nedelja")
WEEKDAYS_EN = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")

TRACK_ALIASES: dict[str, str] = {
    "ai": "AI",
    "umetna inteligenca": "AI",
    "agenti": "AI",
    "azure": "Azure",
    "oblak": "Azure",
    "cloud": "Azure",
    "varnost": "Varnost",
    "security": "Varnost",
    "podatki": "Podatki",
    "data": "Podatki",
    "razvoj": "Razvoj",
    "development": "Razvoj",
    "dev": "Razvoj",
    "microsoft 365": "Microsoft 365",
    "m365": "Microsoft 365",
    "infrastruktura": "Infrastruktura",
    "infrastructure": "Infrastruktura",
    "infra": "Infrastruktura",
    "poslovno": "Poslovno",
    "business": "Poslovno",
    "keynote": "Keynote",
}

COMPACT_FIELDS = ("id", "title", "speaker", "room", "start", "end", "track", "level", "lang")


def normalize_text(value: str) -> str:
    """Lowercase and strip diacritics so ``Varnost`` matches ``varnost`` and ``č`` matches ``c``."""
    decomposed = unicodedata.normalize("NFKD", str(value))
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch)).casefold()


class Program:
    """In-memory view of the program fixture."""

    def __init__(self, data: dict[str, Any], *, path: Path | None = None) -> None:
        self.meta: dict[str, Any] = dict(data.get("meta", {}))
        self.talks: list[dict[str, Any]] = list(data.get("talks", []))
        self.path = path
        self.tz = ZoneInfo(self.meta.get("timezone", "Europe/Ljubljana"))
        self._by_id = {t["id"]: t for t in self.talks}
        self.days: list[str] = list(self.meta.get("days") or sorted({self.day_of(t) for t in self.talks}))

    # ── lookup ──────────────────────────────────────────────────────────

    def get(self, talk_id: str) -> dict[str, Any] | None:
        return self._by_id.get(str(talk_id).strip())

    def day_of(self, talk: dict[str, Any]) -> str:
        return datetime.fromisoformat(talk["start"]).astimezone(self.tz).date().isoformat()

    def day_labels(self) -> dict[str, str]:
        """``{"2026-09-22": "torek"}`` — used by the prompt context and the search day filter."""
        labels = {}
        for day in self.days:
            weekday = datetime.fromisoformat(day).weekday()
            labels[day] = WEEKDAYS_SL[weekday]
        return labels

    def resolve_day(self, value: str | None) -> str | None:
        """Accept ISO dates, Slovene/English weekday names or a bare day number."""
        if value is None or not str(value).strip():
            return None
        text = normalize_text(value).strip().rstrip(".")
        for day in self.days:
            if text == day:
                return day
            weekday = datetime.fromisoformat(day).weekday()
            aliases = {
                normalize_text(WEEKDAYS_SL[weekday]),
                WEEKDAYS_EN[weekday],
                day[-2:],
                day[-2:].lstrip("0"),
                f"{day[-2:].lstrip('0')}.9",
                f"{day[-2:].lstrip('0')}. 9",
            }
            if text in aliases:
                return day
        raise ValueError(
            f"neznan dan {value!r}; možnosti: "
            + ", ".join(f"{d} ({label})" for d, label in self.day_labels().items())
        )

    @staticmethod
    def resolve_track(value: str | None) -> str | None:
        if value is None or not str(value).strip():
            return None
        key = normalize_text(value).strip()
        for alias, track in TRACK_ALIASES.items():
            if key == normalize_text(alias):
                return track
        raise ValueError(
            f"neznan sklop {value!r}; možnosti: " + ", ".join(sorted(set(TRACK_ALIASES.values())))
        )

    # ── search ──────────────────────────────────────────────────────────

    def search(
        self,
        query: str = "",
        *,
        track: str | None = None,
        day: str | None = None,
        room: str | None = None,
        speaker: str | None = None,
        limit: int = 25,
    ) -> list[dict[str, Any]]:
        """Keyword search with optional filters; results sorted by relevance, then time."""
        track_name = self.resolve_track(track)
        day_iso = self.resolve_day(day)
        room_key = normalize_text(room) if room else None
        speaker_key = normalize_text(speaker) if speaker else None
        tokens = [t for t in normalize_text(query).replace(",", " ").split() if len(t) > 1]

        scored: list[tuple[int, str, dict[str, Any]]] = []
        for talk in self.talks:
            if track_name and talk["track"] != track_name:
                continue
            if day_iso and self.day_of(talk) != day_iso:
                continue
            if room_key and room_key not in normalize_text(talk["room"]):
                continue
            if speaker_key and speaker_key not in normalize_text(talk["speaker"]):
                continue
            score = self._score(talk, tokens)
            if tokens and score == 0:
                continue
            scored.append((score, talk["start"], talk))
        scored.sort(key=lambda item: (-item[0], item[1]))
        capped = max(1, min(int(limit) if limit is not None else 25, 80))
        return [self.compact(t) for _, _, t in scored[:capped]]

    @staticmethod
    def _score(talk: dict[str, Any], tokens: list[str]) -> int:
        if not tokens:
            return 0
        title = normalize_text(talk["title"])
        tags = normalize_text(" ".join(talk.get("tags", [])))
        rest = normalize_text(
            " ".join((talk.get("abstract", ""), talk["track"], talk["speaker"], talk["room"]))
        )
        score = 0
        for token in tokens:
            if token in title:
                score += 3
            if token in tags:
                score += 2
            if token in rest:
                score += 1
        return score

    def compact(self, talk: dict[str, Any]) -> dict[str, Any]:
        """The fields the model needs (keeps tool output small)."""
        item = {k: talk[k] for k in COMPACT_FIELDS if k in talk}
        item["day"] = self.day_labels().get(self.day_of(talk), self.day_of(talk))
        if talk.get("synthetic"):
            item["synthetic"] = True
        return item

    def slots(self, talk_ids: Iterable[str]) -> tuple[list[dict[str, Any]], list[str]]:
        """Resolve ids to ``{id,title,room,start,end}`` slots; unknown ids are returned separately."""
        found, unknown = [], []
        for raw in talk_ids:
            talk = self.get(raw)
            if talk is None:
                unknown.append(str(raw))
            else:
                found.append({k: talk[k] for k in ("id", "title", "room", "start", "end")})
        return found, unknown


@lru_cache(maxsize=4)
def _load(path_str: str) -> Program:
    path = Path(path_str)
    if not path.is_file():
        raise FileNotFoundError(
            f"program fixture not found at {path}; run `uv run gen-program` or set NTK_PROGRAM_PATH"
        )
    return Program(json.loads(path.read_text(encoding="utf-8")), path=path)


def load_program(path: str | os.PathLike[str] | None = None) -> Program:
    """Load (and cache) the program from *path*, ``NTK_PROGRAM_PATH`` or the default fixture."""
    chosen = Path(path or os.environ.get("NTK_PROGRAM_PATH") or DEFAULT_PROGRAM_PATH)
    if not chosen.is_absolute():
        chosen = ROOT / chosen
    return _load(str(chosen.resolve()))


__all__ = ["DEFAULT_PROGRAM_PATH", "Program", "load_program", "normalize_text"]
