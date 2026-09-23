import marimo

__generated_with = "0.24.2"
app = marimo.App(width="medium", app_title="Demo 1 · The agent is a graph")


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
            "Demo 1 · The agent is a graph",
            "One LangGraph graph. The same one runs on the laptop and in production.",
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
    The agent takes a request in plain language and returns a conference agenda. It decides which
    tools to call. It answers in Slovene, because its system prompt says so.

    Below: the three tools, the graph that connects them, and a live answer from that graph.
    """)
    return


# ── artefact: the three tools ───────────────────────────────────────────────────────────────────
@app.cell
def _(mo, ntk):
    from agent.tools import default_tools

    def _first_line(doc: str) -> str:
        stripped = (doc or "").strip()
        return stripped.splitlines()[0] if stripped else ""

    _rows = [
        {
            "tool": t.name,
            "what it does": _first_line(t.description),
            "arguments": ", ".join(t.args.keys()) or "(none)",
        }
        for t in default_tools()
    ]
    tools_table = mo.ui.table(
        _rows,
        selection=None,
        label="The agent's three tools — agent.tools.default_tools()",
    )
    tools_table  # noqa: B018 - marimo idiom: a bare UI element displays it in the cell's output
    return


# ── interaction: call a tool by hand — what goes in, what comes out ─────────────────────────────
@app.cell
def _(mo):
    tool_picker = mo.ui.dropdown(
        options=["preferences", "program_search", "clash_checker"],
        value="program_search",
        label="Call a tool by hand",
    )
    tool_picker  # noqa: B018 - marimo idiom: a bare UI element displays it in the cell's output
    return (tool_picker,)


@app.cell
def _(mo, ntk, tool_picker):
    import json as _json

    from agent.tools import clash_checker, preferences, program_search

    def _clashing_ids() -> list[str]:
        # Two AI talks on Tuesday that start at the same time, so the checker has something to report.
        _talks = _json.loads(program_search.invoke({"track": "AI", "day": "torek", "limit": 25}))
        _by_start: dict[str, list[str]] = {}
        for _talk in _talks:
            _by_start.setdefault(_talk["start"], []).append(_talk["id"])
        _pair = next((ids[:2] for ids in _by_start.values() if len(ids) > 1), None)
        return _pair or [t["id"] for t in _talks[:2]]

    _tools = {"preferences": preferences, "program_search": program_search, "clash_checker": clash_checker}
    _args = {
        "preferences": {},
        "program_search": {"track": "AI", "day": "torek", "limit": 3},
        "clash_checker": {"talk_ids": _clashing_ids()},
    }[tool_picker.value]
    _result = _json.loads(_tools[tool_picker.value].invoke(_args))

    def _json_view(value) -> object:
        return mo.ui.code_editor(
            value=_json.dumps(value, ensure_ascii=False, indent=2),
            language="json",
            disabled=True,
            max_height=320,
            show_copy_button=False,
        )

    mo.vstack(
        [
            mo.md(
                f"The model's reply would hold a tool call: the name `{tool_picker.value}` and "
                "these arguments. The tool node runs the function and adds its JSON result to the "
                "conversation as a tool message."
            ),
            mo.hstack(
                [
                    mo.vstack([mo.md("**Goes in** — the arguments"), _json_view(_args)]),
                    mo.vstack([mo.md("**Comes out** — the result"), _json_view(_result)]),
                ],
                widths=[1, 2],
                align="start",
            ),
        ]
    )
    return


# ── artefact: build_graph, as readable code ──────────────────────────────────────────────────────
@app.cell
def _(mo, ntk):
    _code = ntk.source_of("src/agent/graph.py", lines=(35, 108))
    mo.vstack(
        [
            mo.md("**`src/agent/graph.py` — the body of `build_graph`**"),
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


# ── artefact: guard switch + live DAG (Demo 1's money shot) ─────────────────────────────────────
@app.cell
def _(mo):
    guard_switch = mo.ui.switch(value=False, label="guard (enforce_constraints)")
    mo.vstack(
        [
            mo.md("Flip the switch. The graph below is redrawn from the compiled code ⬇️"),
            guard_switch,
        ]
    )
    return (guard_switch,)


@app.cell
def _(guard_switch, mo, ntk):
    _headline = (
        "Guard ON — the graph has one more node: **guard**"
        if guard_switch.value
        else "Guard OFF — two nodes: **assistant → tools**"
    )
    mo.vstack(
        [
            ntk.stage_note(_headline, kind="success" if guard_switch.value else "neutral"),
            mo.mermaid(ntk.dag_mermaid(guard_switch.value)),
        ]
    )
    return


# ── interaction: question, button, live answer ──────────────────────────────────────────────────
@app.cell
def _(mo, ntk):
    from scripts.act1 import ACT1_QUESTION_EN

    question_box = mo.ui.text_area(
        value=ACT1_QUESTION_EN,
        label="Question for the agent (editable)",
        rows=3,
        full_width=True,
    )
    question_box  # noqa: B018 - marimo idiom: a bare UI element displays it in the cell's output
    return (question_box,)


@app.cell
def _(mo):
    run_button = mo.ui.run_button(label="▶ Ask the agent (local server :8088)")
    run_button  # noqa: B018 - marimo idiom: a bare UI element displays it in the cell's output
    return (run_button,)


@app.cell
def _(mo, ntk, question_box, run_button):
    from scripts.act1 import ask, output_text, tool_calls

    from agent.contract import extract_agenda, resolve_items
    from agent.program import load_program

    def _live_answer() -> dict:
        _start = ntk.now_seconds()
        _response = ask(8088, question_box.value, timeout=180)
        _elapsed = ntk.now_seconds() - _start
        return {
            "question": question_box.value,
            "answer": output_text(_response),
            "tool_calls": tool_calls(_response),
            "response_id": _response.get("id"),
            "elapsed_seconds": round(_elapsed, 1),
        }

    if run_button.value or ntk.OFFLINE:
        _payload = ntk.cached("act1", _live_answer, timeout=ntk.LOCAL_MODEL_TIMEOUT)
        if "error" in _payload:
            _out = ntk.stage_note(_payload["error"], kind="danger")
        else:
            if ntk.OFFLINE:
                _source = "cached (NTK_DEMO_OFFLINE=1, no network)"
            elif _payload.get("_stale"):
                _source = f"cached — the live call failed: {_payload.get('_note', '')}"
            else:
                _source = f"live call to :8088 ({_payload.get('elapsed_seconds', '?')} s)"
            _agenda = extract_agenda(_payload.get("answer", ""))
            _program = load_program()
            _resolved = resolve_items(_agenda, _program.get) if _agenda else None
            _items_table = (
                mo.ui.table(_resolved["items"], selection=None, label="Resolved agenda")
                if _resolved
                else mo.md("_The agent returned no agenda._")
            )
            _calls = ", ".join(_payload.get("tool_calls", [])) or "(none)"
            _out = mo.vstack(
                [
                    mo.md(f"**Source:** {_source}"),
                    mo.md(_payload.get("answer") or "_(no answer)_"),
                    mo.md(f"**Tools called:** {_calls}"),
                    _items_table,
                ]
            )
    else:
        _out = mo.md("_Press the button above to ask the agent._")
    _out  # noqa: B018 - marimo idiom: a bare value displays it in the cell's output
    return


# ── takeaway: purity ────────────────────────────────────────────────────────────────────────────
@app.cell
def _(mo, ntk):
    _test_src = ntk.source_of("tests/test_purity.py", lines=(1, 18))
    mo.vstack(
        [
            ntk.stage_note(
                "**`src/agent` imports no Azure or Foundry code.** The same graph runs locally "
                "(above) and in production on Foundry. A test enforces it.",
                kind="success",
            ),
            mo.ui.code_editor(
                value=_test_src,
                language="python",
                disabled=True,
                max_height=260,
                show_copy_button=False,
            ),
        ]
    )
    return


if __name__ == "__main__":
    app.run()
