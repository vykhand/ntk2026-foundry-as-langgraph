import marimo

__generated_with = "0.24.2"
app = marimo.App(width="medium", app_title="Demo 4 · Agent se ujame")


@app.cell
def _():
    import marimo as mo

    return (mo,)


@app.cell
def _():
    import sys as _sys
    from pathlib import Path as _Path

    # The Slovene copies live one level down; the house module is notebooks/_ntk.py.
    _sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))
    import _ntk as ntk

    return (ntk,)


# ── title ──────────────────────────────────────────────────────────────────────────────────────
@app.cell
def _(mo, ntk):
    _pieces = [
        ntk.banner(
            "Demo 4 · Agent se ujame",
            "Isti graf, en dodaten vozel — past, ki jo ta vozel ujame.",
        )
    ]
    _offline = ntk.offline_note("sl")
    if _offline is not None:
        _pieces.append(_offline)
    mo.vstack(_pieces)
    return


# ── framing ──────────────────────────────────────────────────────────────────────────────────────
@app.cell
def _(mo):
    mo.md(r"""
    Trije zagoni istega vprašanja povedo več kot razlika med različnimi vprašanji — to je past,
    v katero se je model ujel sam. Rešitev ni bil boljši prompt, ker noben prompt ni pomagal;
    rešitev je en dodaten korak v grafu.

    Najprej past. Potem vozlišče, ki jo lovi — v grafu, ne v promptu. Nazadnje pravi agent, ki
    teče v produkciji: kako napiše slab urnik in ga sam popravi, še preden ga vidimo.
    """)
    return


# ── artefact: lažna zmaga ──────────────────────────────────────────────────────────────────────
@app.cell
def _(mo, ntk):
    mo.vstack(
        [
            ntk.stage_note(
                "**Isti prompt, trije zagoni** — razpon med zagoni istega prompta je večji od "
                "razlike med prompti. Graf je pravi, iz `evals/results/`, izrisan z "
                "`uv run eval-variance` (`scripts/eval_variance.py`) — ta demo ga ne poganja znova.",
                kind="warn",
            ),
            mo.image(src=str(ntk.ROOT / "deck" / "assets" / "eval-variance.svg"), width=720),
        ]
    )
    return


# ── artefact: guard_node, kot berljiva koda ──────────────────────────────────────────────────────
@app.cell
def _(mo, ntk):
    _code = ntk.source_of("src/agent/graph.py", lines=(51, 84))
    mo.vstack(
        [
            mo.md("**`src/agent/graph.py` — telo `guard_node`**"),
            mo.ui.code_editor(
                value=_code,
                language="python",
                disabled=True,
                max_height=380,
                show_copy_button=False,
            ),
        ]
    )
    return


# ── artefact: pravilo, ki ga guard uveljavlja ────────────────────────────────────────────────────
@app.cell
def _(mo, ntk):
    _code = ntk.source_of("src/agent/guard.py", lines=(142, 217))
    mo.vstack(
        [
            mo.md("**`src/agent/guard.py` — pravilo, ki ga `inspect` uveljavlja**"),
            mo.ui.code_editor(
                value=_code,
                language="python",
                disabled=True,
                max_height=420,
                show_copy_button=False,
            ),
        ]
    )
    return


# ── artefact: DAG z vozliščem guard ──────────────────────────────────────────────────────────────
@app.cell
def _(mo, ntk):
    mo.vstack(
        [
            ntk.stage_note("Guard je vozlišče v grafu — ne stavek v promptu.", kind="success"),
            mo.mermaid(ntk.dag_mermaid(True)),
        ]
    )
    return


# ── interaction: vprašanje in gumb ───────────────────────────────────────────────────────────────
@app.cell
def _(mo):
    ACT4_QUESTION = "Nina tukaj — v torek bi šla na čim več predavanj o podatkih."
    mo.md(f"**Vprašanje, na katerem smo past ujeli ponovljivo:** {ACT4_QUESTION}")
    return (ACT4_QUESTION,)


@app.cell
def _(mo):
    run_button = mo.ui.run_button(label="▶ Poglej, kako se agent ujame")
    run_button  # noqa: B018 - marimo idiom: a bare UI element displays it in the cell's output
    return (run_button,)


# ── interaction: prvi osnutek in popravek, drug ob drugem (money shot demota 4) ───────────────────
@app.cell
def _(ACT4_QUESTION, mo, ntk, run_button):
    from agent.contract import resolve_items
    from agent.program import load_program

    def _live_invoke() -> dict:
        """A real ``azd ai agent invoke`` call — the one BRIEF.md lists as fine to run live.

        Only reached when the button is clicked with the network up; offline runs never call
        this (``ntk.cached`` returns straight from the cache file), and a slow/failed call falls
        back to the cached draft-then-repair capture instead of hanging the cell.
        """
        import os
        import re
        import subprocess

        proc = subprocess.run(
            [
                "azd",
                "ai",
                "agent",
                "invoke",
                "ntk-asistent",
                "--new-session",
                "--new-conversation",
                ACT4_QUESTION,
            ],
            cwd=ntk.ROOT,
            env={**os.environ, "AZD_SKIP_UPDATE_CHECK": "true"},
            capture_output=True,
            text=True,
            timeout=40,
        )
        stdout = proc.stdout.strip()
        _match = re.search(r"^Session:\s*([0-9a-fA-F]{8,})", stdout, re.MULTILINE)
        return {
            "question": ACT4_QUESTION,
            "answer": stdout,
            "session_id": _match.group(1) if _match else None,
            "tool_calls": [],
        }

    if run_button.value or ntk.OFFLINE:
        _payload = ntk.cached("act4-invoke", _live_invoke, timeout=40)
        if "error" in _payload:
            _out = ntk.stage_note(_payload["error"], kind="danger")
        else:
            _agendas = ntk.all_agendas(_payload.get("answer", ""))
            _program = load_program()
            if len(_agendas) >= 2:
                _draft_items = resolve_items(_agendas[0], _program.get)["items"]
                _fixed_items = resolve_items(_agendas[-1], _program.get)["items"]
                _tables = mo.hstack(
                    [
                        mo.vstack(
                            [
                                mo.md("**Prvi osnutek** — guard ga zavrne"),
                                mo.ui.table(_draft_items, selection=None),
                            ]
                        ),
                        mo.vstack(
                            [
                                mo.md("**Popravljen urnik**"),
                                mo.ui.table(_fixed_items, selection=None),
                            ]
                        ),
                    ]
                )
            else:
                _tables = mo.md("_Ta zagon ni imel česa popraviti — en sam urnik v odgovoru._")
            if ntk.OFFLINE:
                _source = "predpomnjeno (NTK_DEMO_OFFLINE=1, brez omrežja)"
            elif _payload.get("_stale"):
                _source = f"predpomnjeno — živ klic ni uspel: {_payload.get('_note', '')}"
            else:
                _source = "živ klic (`azd ai agent invoke`)"
            _out = mo.vstack([mo.md(f"**Vir odgovora:** {_source}"), _tables])
    else:
        _out = mo.md("_Pritisnite gumb zgoraj, da vidite past in popravek._")
    _out  # noqa: B018 - marimo idiom: a bare value displays it in the cell's output
    return


# ── stage note: znan rob primera ─────────────────────────────────────────────────────────────────
@app.cell
def _(ntk):
    ntk.stage_note(
        "**En zagon od osmih** je popravljeni urnik vrnil prazen (`\"items\": []`) namesto "
        "predavanja, ki bi ustrezalo — guard tega ne ujame, ker prazen urnik ne krši nobenega "
        "pravila (`the talk's write-up`, vnos S-09). Če se to zgodi v živo, povejte občinstvu, kaj se "
        "je zgodilo — to je znan rob primera, ne nov hrošč.",
        kind="warn",
    )
    return


# ── artefact: guardove lastne odločitve ──────────────────────────────────────────────────────────
@app.cell
def _(mo, ntk):
    import json

    _monitor_path = ntk.cache_path("act4-monitor")
    _monitor = (
        json.loads(_monitor_path.read_text(encoding="utf-8"))
        if _monitor_path.exists()
        else {"session_id": None, "lines": []}
    )
    _rows = []
    for _line in _monitor.get("lines", []):
        _verdict = json.loads(_line[len("[guard] ") :]) if _line.startswith("[guard] ") else {}
        _rows.append(
            {
                "odločitev": _verdict.get("decision", "?"),
                "vir udeleženca": _verdict.get("attendee_source", "?"),
                "težave": "; ".join(_verdict.get("problems", [])) or "(brez)",
            }
        )
    verdicts_table = mo.ui.table(_rows, selection=None, label='Guardove odločitve — `[guard] {...}`')
    mo.vstack(
        [
            mo.md(
                "Produkcijska pot bere te vrstice z `azd ai agent monitor --session-id <id> | "
                'grep "[guard]"` — ukaz je tu zaradi razlage; podatki spodaj so predpomnjeni, ker '
                "razširitev na odru ni vedno zanesljiva (ista seja se ni vedno shranila)."
            ),
            verdicts_table,
        ]
    )
    return


# ── takeaway: sklep ───────────────────────────────────────────────────────────────────────────────
@app.cell
def _(ntk):
    ntk.stage_note(
        "**To ni boljši prompt.** To je determinističen Python preverjevalec nad izpisom modela — "
        "isti graf, en dodaten vozel. Model je lahko še vedno nezanesljiv; preverba ni.",
        kind="success",
    )
    return


if __name__ == "__main__":
    app.run()
