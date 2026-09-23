import marimo

__generated_with = "0.24.2"
app = marimo.App(width="medium", app_title="Demo 3 · Traces and sandboxes")


@app.cell
def _():
    import marimo as mo

    return (mo,)


@app.cell
def _():
    import _ntk as ntk

    return (ntk,)


# ── title ──────────────────────────────────────────────────────────────────────────────────────
@app.cell
def _(mo, ntk):
    _pieces = [
        ntk.banner(
            "Demo 3 · Traces and sandboxes",
            "Provided by the platform. None of it is in my code.",
        )
    ]
    _offline = ntk.offline_note()
    if _offline is not None:
        _pieces.append(_offline)
    mo.vstack(_pieces)
    return


# ── framing (60 % of the room is non-technical — one step at a time) ─────────────────────────────
@app.cell
def _(mo):
    mo.md(r"""
    Each conversation with the agent runs in its own sandbox, and each call leaves a trace. The
    repository has no logging code for either.

    First, one call broken into spans, as Application Insights records them. Then two
    conversations side by side: the same agent, and the second one knows nothing about the first.
    """)
    return


# ── artefact: the query I get for free ──────────────────────────────────────────────────────────
@app.cell
def _(mo, ntk):
    _code = ntk.source_of("scripts/act3.py", lines=(64, 70))
    mo.vstack(
        [
            mo.md(
                "**`scripts/act3.py`** — the KQL query `uv run act3 --kql` runs against "
                "Application Insights. I wrote the query; the OpenTelemetry distro collected "
                "the spans."
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


# ── artefact: one call, broken into spans (money shot 1) ────────────────────────────────────────
@app.cell
def _(ntk):
    def _live_trace() -> dict:
        import os

        workspace = os.environ.get("NTK_LOG_ANALYTICS_WORKSPACE_ID", "").strip()
        if not workspace:
            raise RuntimeError("NTK_LOG_ANALYTICS_WORKSPACE_ID is not set — no workspace to query")
        from scripts.act3 import query_app_insights

        rows = query_app_insights(workspace_id=workspace, minutes=15, limit=60)
        if not rows:
            raise RuntimeError("no spans in the last 15 minutes")
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
                "span": ("  " * s["depth"]) + s["name"],
                "kind": s["kind"],
                "gen_ai op": s["op"] or "-",
                "duration (ms)": round(s["duration_ms"]),
                "bar": _bar(s["duration_ms"], _total_ms),
            }
            for s in _spans
        ]
        _table = mo.ui.table(_rows, selection=None, label="One agent call, broken into spans")
        _summary = ntk.stage_note(
            f"**{len(_spans)} spans · {_chat_calls} model calls · {_tool_calls} tool calls** — "
            f"the whole call took {_total_ms / 1000:.1f} s. None of it was instrumented by hand "
            f"(source: `{trace_payload.get('source', '?')}`).",
            kind="success",
        )
        _out = mo.vstack([_table, _summary])
    _out  # noqa: B018 - marimo idiom: a bare value displays it in the cell's output
    return


# ── artefact: portal screenshots, in case the network is slow ───────────────────────────────────
@app.cell
def _(mo, ntk):
    _list_path = str(ntk.ROOT / "notebooks/assets/portal-07-traces-list.jpg")
    _waterfall_path = str(ntk.ROOT / "notebooks/assets/portal-08-trace-waterfall.jpg")
    mo.vstack(
        [
            ntk.stage_note(
                "Fallback if the portal is slow: two screenshots from a real session on "
                "2026-09-06.",
                kind="neutral",
            ),
            mo.hstack(
                [
                    mo.vstack([mo.image(src=_list_path, width=520), mo.md("_Trace list_")]),
                    mo.vstack(
                        [mo.image(src=_waterfall_path, width=520), mo.md("_One call's waterfall_")]
                    ),
                ],
                justify="space-around",
            ),
        ]
    )
    return


# ── interaction: two sandboxes, side by side (money shot 2) ─────────────────────────────────────
@app.cell
def _(ntk):
    ntk.stage_note(
        "Two buttons, two separate conversations. Neither sends the other's "
        "`previous_response_id`, so neither sees the other's history.",
        kind="info",
    )
    return


@app.cell
def _(mo):
    session_a_button = mo.ui.run_button(label="▶ Open conversation A · Nina (local server :8088)")
    session_a_button  # noqa: B018 - marimo idiom: a bare UI element displays it in the cell's output
    return (session_a_button,)


@app.cell
def _(mo):
    session_b_button = mo.ui.run_button(
        label="▶ Open conversation B · new visitor (local server :8088)"
    )
    session_b_button  # noqa: B018 - marimo idiom: a bare UI element displays it in the cell's output
    return (session_b_button,)


@app.cell
def _(mo, ntk):
    from scripts.act1 import ask, output_text, tool_calls

    SESSION_QUESTION_A = (
        "My name is Nina. I want as many AI talks as possible on Tuesday, nothing before nine."
    )
    SESSION_QUESTION_B = "Do you know my name, and what I just asked in the other conversation?"

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
            _hint = mo.md("_Press the button above to open this conversation._")
            return mo.vstack([mo.md(f"**{label}**"), _hint])
        _payload = ntk.cached(cache_key, lambda: _call(question), timeout=ntk.LOCAL_MODEL_TIMEOUT)
        if "error" in _payload:
            return mo.vstack([mo.md(f"**{label}**"), ntk.stage_note(_payload["error"], kind="danger")])
        _calls = ", ".join(_payload.get("tool_calls", [])) or "(none)"
        return mo.vstack(
            [
                mo.md(f"**{label}** · response id: `{_payload.get('response_id', '?')}`"),
                mo.md(f"*{_payload.get('question', '')}*"),
                mo.md(_payload.get("answer") or "_(no answer)_"),
                mo.md(f"**Tools called:** {_calls}"),
            ]
        )

    return SESSION_QUESTION_A, SESSION_QUESTION_B, session_panel


# One cell per conversation, on purpose. A run_button reads True only for the run its click triggers
# and False again afterwards — so with both panels in one cell, opening B re-ran that cell and wiped
# A's answer off the screen, which is exactly the side-by-side this demo is about.
@app.cell
def _(SESSION_QUESTION_A, session_a_button, session_panel):
    panel_a = session_panel("Conversation A", session_a_button, "act3-session-a", SESSION_QUESTION_A)
    return (panel_a,)


@app.cell
def _(SESSION_QUESTION_B, session_b_button, session_panel):
    panel_b = session_panel("Conversation B", session_b_button, "act3-session-b", SESSION_QUESTION_B)
    return (panel_b,)


@app.cell
def _(mo, panel_a, panel_b):
    _out = mo.hstack([panel_a, panel_b], justify="space-around", align="start", wrap=True)
    _out  # noqa: B018 - marimo idiom: a bare value displays it in the cell's output
    return


# ── takeaway: what I did not write ──────────────────────────────────────────────────────────────
@app.cell
def _(ntk):
    ntk.stage_note(
        "**The agent's identity, the session sandbox, the trace of each call: I wrote none of "
        "them.** On Foundry the platform provides all three.",
        kind="success",
    )
    return


if __name__ == "__main__":
    app.run()
