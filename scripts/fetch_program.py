"""Replace the synthetic stand-in with the real NT konferenca 2026 programme from ntk.si.

    uv run fetch-program                 # pull https://www.ntk.si/api/clientapi/schedule
    uv run fetch-program --from api.json # normalise a saved copy instead
    uv run fetch-program --check         # exit 1 if the committed fixture is stale

The schedule page is a client-rendered app; its data comes from one public JSON endpoint, and this
script normalises that into ``fixtures/program.json`` so the agent keeps reading one file
(scenario spec §Data plan 2). Nothing about the agent, the tools, the personas or the evaluators
has to change — which is the point of having had a schema before the data existed.

What is deliberately *not* copied: speaker biographies, photos, LinkedIn and company fields. The
agent needs a name to say out loud, not a profile, and a demo repository is no place to mirror
personal data just because a website exposes it.

Two decisions live in the mapping:

* **Ten ntk.si tracks fold into the fixture's nine short ones** (``TRACKS``). The personas, the
  golden set and the track aliases all speak in the short names; the official track name is kept
  as a tag, so searching for "identitete" or "DevOps" still finds the talk.
* **The planted joke talk survives the swap** (``JOKE``) — the one ``synthetic: true`` entry, in a
  room ntk.si does not schedule, so it can never double-book a real speaker's slot.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "fixtures" / "program.json"
SCHEMA = ROOT / "fixtures" / "program.schema.json"
API = "https://www.ntk.si/api/clientapi/schedule"

CONFERENCE_ID = 1  # "NT 2026"; business-day and partner events carry it too
SESSION_KIND = 1001  # "Predavanje" — lunches, breaks and parties are not talks
OFFSET = "+02:00"  # CEST all three days; the API sends naive local times

# ntk.si track id → the fixture's short track name.
TRACKS = {
    3: "AI",  # Umetna inteligenca in poslovne rešitve
    7: "Azure",  # Azure okolja in Hibridni oblak
    8: "Varnost",  # Omrežja, varnost in identitete
    5: "Podatki",  # Podatki in analitika
    1: "Razvoj",  # Razvoj aplikacij
    2: "Razvoj",  # DevOps, razvojna orodja in arhitektura
    4: "Microsoft 365",  # Produktivnost uporabnikov
    6: "Infrastruktura",  # Strežniki in upravljanje
    9: "Poslovno",  # Poslovni dan
    12: "Poslovno",  # Mind Upgrade
}
LEVELS = {"100": 100, "200": 200, "300": 300, "400": 400, "Business": 100}

JOKE = {
    "title": "Digitalna transformacija digitalne transformacije 2.0",
    "speaker": "dr. Sinergija Paradigma",
    "room": "Tartini",
    "start": f"2026-09-22T11:00:00{OFFSET}",
    "end": f"2026-09-22T11:45:00{OFFSET}",
    "track": "Poslovno",
    "level": 100,
    "demo_pct": 0,
    "lang": "sl",
    "synthetic": True,
    "tags": ["digitalna-transformacija", "sinergija", "paradigma", "poslovno"],
    "abstract": "Holistična sinergija disruptivnih paradigm v postdigitalni dobi transformacije.",
}


def _clean(text: str | None) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def fetch(source: Path | None) -> dict:
    if source is not None:
        return json.loads(source.read_text(encoding="utf-8"))
    request = urllib.request.Request(API, headers={"User-Agent": "ntk2026-foundry-as-langgraph"})
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)


def normalize(raw: dict) -> dict:
    speakers = {s["id"]: _clean(f"{s['firstName']} {s['lastName']}") for s in raw["speakers"]}
    rooms = {r["id"]: _clean(r["name"]) for r in raw["rooms"]}
    track_names = {t["id"]: _clean(t["name"]) for t in raw["tracks"]}
    levels = {lv["id"]: lv["name"] for lv in raw["levels"]}
    products = {p["id"]: _clean(p["name"]) for p in raw["products"]}

    talks = []
    for event in raw["events"]:
        if event["kindId"] != SESSION_KIND or event["isCanceled"]:
            continue
        if CONFERENCE_ID not in event["conferenceIds"]:
            continue
        tags = [products[p] for p in event["productIds"] if p in products]
        tags.append(track_names[event["trackId"]])
        talks.append(
            {
                "id": "",  # assigned after the chronological sort, as the synthetic fixture did
                "title": _clean(event["name"]),
                "speaker": ", ".join(speakers[s] for s in event["speakers"]),
                "room": rooms[event["roomId"]],
                "start": event["startTime"][:19] + OFFSET,
                "end": event["endTime"][:19] + OFFSET,
                "track": TRACKS[event["trackId"]],
                "level": LEVELS[levels[event["levelId"]]],
                "demo_pct": max(0, min(100, int(event["demo"] or 0))),
                "lang": "en" if event["isEnglish"] else "sl",
                "synthetic": False,
                "tags": list(dict.fromkeys(tags)),
                "abstract": _clean(event["description"]),
            }
        )

    taken = {(t["room"], t["start"]) for t in talks}
    assert (JOKE["room"], JOKE["start"]) not in taken, "the joke talk would double-book a real room"
    talks.append(dict(JOKE, id=""))
    talks.sort(key=lambda t: (t["start"], t["room"]))
    for n, talk in enumerate(talks, start=1):
        talk["id"] = f"t-{n:03d}"

    days = sorted({t["start"][:10] for t in talks})
    return {
        "meta": {
            "source": "ntk.si-export",
            "generated_at": raw.get("created", "")[:10],
            "conference": "NT konferenca 2026",
            "venue": "Grand Hotel Bernardin, Portorož",
            "timezone": "Europe/Ljubljana",
            "days": days,
            "note": (
                f"The real programme from {API} (hash {raw.get('hash', '?')}), normalised by "
                "scripts/fetch_program.py: talks only, names only — no biographies, photos or "
                "profile links. Exactly one talk carries synthetic=true: the planted joke target, "
                "in a room ntk.si does not schedule."
            ),
        },
        "talks": talks,
    }


def validate(program: dict) -> None:
    import jsonschema

    jsonschema.validate(program, json.loads(SCHEMA.read_text(encoding="utf-8")))


def _render(program: dict) -> str:
    return json.dumps(program, ensure_ascii=False, indent=2) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Normalise the ntk.si programme into the fixture")
    parser.add_argument("--from", dest="source", type=Path, help="a saved API response, not the live one")
    parser.add_argument("--check", action="store_true", help="exit 1 if the fixture differs from ntk.si")
    args = parser.parse_args(argv)

    program = normalize(fetch(args.source))
    validate(program)

    if args.check:
        current = json.loads(OUT.read_text(encoding="utf-8"))
        # generated_at and the hash move on every publish; the talks are what the agent reads.
        stale = current["talks"] != program["talks"]
        print("program: stale — run `uv run fetch-program`" if stale else "program: up to date")
        return 1 if stale else 0

    OUT.write_text(_render(program), encoding="utf-8")
    by_day: dict[str, int] = {}
    for talk in program["talks"]:
        by_day[talk["start"][:10]] = by_day.get(talk["start"][:10], 0) + 1
    joke = [t["id"] for t in program["talks"] if t["synthetic"]]
    print(f"wrote {OUT.relative_to(ROOT)}: {len(program['talks'])} talks {by_day}; synthetic={joke}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
