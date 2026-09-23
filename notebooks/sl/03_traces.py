import marimo

__generated_with = "0.24.2"
app = marimo.App(width="medium", app_title="Demo 3 · Sledi in peskovniki")


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
            "Demo 3 · Sledi in peskovniki",
            "Kar dobim od platforme, ne da bi karkoli od tega sam napisal.",
        )
    ]
    _offline = ntk.offline_note("sl")
    if _offline is not None:
        _pieces.append(_offline)
    mo.vstack(_pieces)
    return


# ── framing (60 % dvorane je netehnične — počasi, korak za korakom) ─────────────────────────────
@app.cell
def _(mo):
    mo.md(r"""
    Vsak pogovor z agentom teče v svojem peskovniku, in vsak klic pusti sled — ne da bi jaz dodal
    eno samo vrstico kode za beleženje. Najprej pogled od znotraj: en klic, razčlenjen na razpone
    (spans), kot jih vidim v Application Insights.

    Potem dva pogovora, drug ob drugem. Oba kličeta istega agenta — a drugi o prvem ne ve ničesar.
    """)
    return


# ── artefact: poizvedba, ki jo dobim zastonj ─────────────────────────────────────────────────────
@app.cell
def _(mo, ntk):
    _code = ntk.source_of("scripts/act3.py", lines=(64, 70))
    mo.vstack(
        [
            mo.md(
                "**`scripts/act3.py`** — ista poizvedba KQL, ki jo `uv run act3 --kql` požene "
                "proti Application Insights; jaz sem napisal te vrstice, razpone pa je nabral "
                "OpenTelemetry distro sam."
            ),
            mo.ui.code_editor(
                value=_code,
                language="python",
                disabled=True,
                max_height=170,
                show_copy_button=False,
            ),
        ]
    )
    return


# ── artefact: en klic, razčlenjen na razpone (money shot 1) ─────────────────────────────────────
@app.cell
def _(ntk):
    def _live_trace() -> dict:
        import os

        workspace = os.environ.get("NTK_LOG_ANALYTICS_WORKSPACE_ID", "").strip()
        if not workspace:
            raise RuntimeError("NTK_LOG_ANALYTICS_WORKSPACE_ID ni nastavljen — ni delovnega prostora")
        from scripts.act3 import query_app_insights

        rows = query_app_insights(workspace_id=workspace, minutes=15, limit=60)
        if not rows:
            raise RuntimeError("v zadnjih 15 minutah ni razponov")
        rows = sorted(rows, key=lambda r: str(r.get("timestamp", "")))
        spans = [
            {
                "name": str(r.get("name", "")),
                "kind": str(r.get("itemType", "")),
                "op": str(r.get("op") or ""),
                "depth": 0,
                "start_ms": i * 20,
                "duration_ms": float(r.get("duration") or 0),
            }
            for i, r in enumerate(rows)
        ]
        return {"source": "kql-live", "spans": spans}

    trace_payload = ntk.cached("act3-trace", _live_trace, timeout=6.0)
    return (trace_payload,)


@app.cell
def _(mo, ntk, trace_payload):
    def _bar(duration_ms: float, total_ms: float, width: int = 24) -> str:
        if not total_ms:
            return ""
        return "█" * max(1, round(width * duration_ms / total_ms))

    if "error" in trace_payload:
        _out = ntk.stage_note(trace_payload["error"], kind="danger")
    else:
        _spans = trace_payload["spans"]
        _total_ms = max(s["start_ms"] + s["duration_ms"] for s in _spans) - min(
            s["start_ms"] for s in _spans
        )
        _chat_calls = sum(1 for s in _spans if s["op"] == "chat")
        _tool_calls = sum(1 for s in _spans if s["op"] == "execute_tool")
        _rows = [
            {
                "vozlišče": ("  " * s["depth"]) + s["name"],
                "vrsta": s["kind"],
                "gen_ai op": s["op"] or "-",
                "trajanje (ms)": round(s["duration_ms"]),
                "graf": _bar(s["duration_ms"], _total_ms),
            }
            for s in _spans
        ]
        _table = mo.ui.table(
            _rows, selection=None, label="En klic agentu, razčlenjen na razpone (spans)"
        )
        _summary = ntk.stage_note(
            f"**{len(_spans)} razponov · {_chat_calls} klici modela · {_tool_calls} klici "
            f"orodij** — ves ta klic je trajal {_total_ms / 1000:.1f} s. Nič od tega nisem "
            f"instrumentiral sam (vir: `{trace_payload.get('source', '?')}`).",
            kind="success",
        )
        _out = mo.vstack([_table, _summary])
    _out  # noqa: B018 - marimo idiom: a bare value displays it in the cell's output
    return


# ── artefact: posnetka portala, če je omrežje počasno ───────────────────────────────────────────
@app.cell
def _(mo, ntk):
    _list_path = str(ntk.ROOT / "notebooks/assets/portal-07-traces-list.jpg")
    _waterfall_path = str(ntk.ROOT / "notebooks/assets/portal-08-trace-waterfall.jpg")
    mo.vstack(
        [
            ntk.stage_note(
                "Če je omrežje počasno ali se portal ne naloži pravočasno — dva posnetka "
                "zaslona iz resnične seje 2026-09-06.",
                kind="neutral",
            ),
            mo.hstack(
                [
                    mo.vstack([mo.image(src=_list_path, width=520), mo.md("_Seznam sledi_")]),
                    mo.vstack(
                        [mo.image(src=_waterfall_path, width=520), mo.md("_Waterfall enega klica_")]
                    ),
                ],
                justify="space-around",
            ),
        ]
    )
    return


# ── interaction: dva peskovnika, druga ob drugi (money shot 2) ──────────────────────────────────
@app.cell
def _(ntk):
    ntk.stage_note(
        "Dva gumba, dva ločena pogovora. Noben ne pošlje `previous_response_id` drugega, "
        "zato noben ne vidi zgodovine drugega.",
        kind="info",
    )
    return


@app.cell
def _(mo):
    session_a_button = mo.ui.run_button(label="▶ Odpri pogovor A · Nina (lokalni strežnik :8088)")
    session_a_button  # noqa: B018 - marimo idiom: a bare UI element displays it in the cell's output
    return (session_a_button,)


@app.cell
def _(mo):
    session_b_button = mo.ui.run_button(
        label="▶ Odpri pogovor B · nov obiskovalec (lokalni strežnik :8088)"
    )
    session_b_button  # noqa: B018 - marimo idiom: a bare UI element displays it in the cell's output
    return (session_b_button,)


@app.cell
def _(mo, ntk):
    from scripts.act1 import ask, output_text, tool_calls

    SESSION_QUESTION_A = "Ime mi je Nina. Zanima me čim več predavanj o AI v torek, brez izpita pred deveto."
    SESSION_QUESTION_B = "Ali veš, kako mi je ime, in kaj sem pravkar vprašal(a) v drugem pogovoru?"

    def _call(question: str) -> dict:
        _start = ntk.now_seconds()
        _response = ask(8088, question, timeout=180)
        _elapsed = ntk.now_seconds() - _start
        return {
            "question": question,
            "answer": output_text(_response),
            "tool_calls": tool_calls(_response),
            "response_id": _response.get("id"),
            "elapsed_seconds": round(_elapsed, 1),
        }

    def session_panel(label: str, button, cache_key: str, question: str):
        if not (button.value or ntk.OFFLINE):
            _hint = mo.md("_Pritisnite gumb zgoraj, da odprete ta pogovor._")
            return mo.vstack([mo.md(f"**{label}**"), _hint])
        _payload = ntk.cached(cache_key, lambda: _call(question), timeout=ntk.LOCAL_MODEL_TIMEOUT)
        if "error" in _payload:
            return mo.vstack([mo.md(f"**{label}**"), ntk.stage_note(_payload["error"], kind="danger")])
        _calls = ", ".join(_payload.get("tool_calls", [])) or "(nobeno)"
        return mo.vstack(
            [
                mo.md(f"**{label}** · response id: `{_payload.get('response_id', '?')}`"),
                mo.md(f"*{_payload.get('question', '')}*"),
                mo.md(_payload.get("answer") or "_(brez odgovora)_"),
                mo.md(f"**Klicana orodja:** {_calls}"),
            ]
        )

    return SESSION_QUESTION_A, SESSION_QUESTION_B, session_panel


# One cell per session, on purpose. A run_button reads True only for the run its click triggers and
# False again afterwards — so with both panels in one cell, opening B re-ran that cell and
# wiped A's answer off the screen, which is exactly the side-by-side this demo is about.
@app.cell
def _(SESSION_QUESTION_A, session_a_button, session_panel):
    panel_a = session_panel("Pogovor A", session_a_button, "act3-session-a-sl", SESSION_QUESTION_A)
    return (panel_a,)


@app.cell
def _(SESSION_QUESTION_B, session_b_button, session_panel):
    panel_b = session_panel("Pogovor B", session_b_button, "act3-session-b-sl", SESSION_QUESTION_B)
    return (panel_b,)


@app.cell
def _(mo, panel_a, panel_b):
    _out = mo.hstack([panel_a, panel_b], justify="space-around", align="start", wrap=True)
    _out  # noqa: B018 - marimo idiom: a bare value displays it in the cell's output
    return


# ── takeaway: kar nisem napisal jaz ──────────────────────────────────────────────────────────────
@app.cell
def _(ntk):
    ntk.stage_note(
        "**Identiteta agenta, peskovnik seje in sled vsakega klica — nič od tega nisem napisal "
        "jaz.** V Foundryju jih da platforma.",
        kind="success",
    )
    return


if __name__ == "__main__":
    app.run()
