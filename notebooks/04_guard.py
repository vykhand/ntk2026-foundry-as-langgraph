import marimo

__generated_with = "0.24.2"
app = marimo.App(width="medium", app_title="Demo 4 · The agent catches itself")


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
            "Demo 4 · The agent catches itself",
            "The same graph with one more node, and the trap that node catches.",
        )
    ]
    _offline = ntk.offline_note()
    if _offline is not None:
        _pieces.append(_offline)
    mo.vstack(_pieces)
    return


# ── framing ──────────────────────────────────────────────────────────────────────────────────────
@app.cell
def _(mo):
    mo.md(r"""
    Three runs of the same prompt differ more than two different prompts do. A better prompt did
    not fix the agent. One more step in the graph did.

    Order: the trap, the node that catches it, then the deployed agent writing a bad agenda and
    repairing it in the same turn.
    """)
    return


# ── artefact: the fake win ──────────────────────────────────────────────────────────────────────
@app.cell
def _(mo, ntk):
    mo.vstack(
        [
            ntk.stage_note(
                "**Same prompt, three runs.** The spread between runs of one prompt is wider than "
                "the difference between prompts. The chart is real, from `evals/results/`, drawn "
                "by `uv run eval-variance` (`scripts/eval_variance.py`); this demo does not re-run it.",
                kind="warn",
            ),
            mo.image(src=str(ntk.ROOT / "deck" / "assets" / "eval-variance.svg"), width=720),
        ]
    )
    return


# ── artefact: guard_node, as readable code ──────────────────────────────────────────────────────
@app.cell
def _(mo, ntk):
    _code = ntk.source_of("src/agent/graph.py", lines=(51, 84))
    mo.vstack(
        [
            mo.md("**`src/agent/graph.py` — the body of `guard_node`**"),
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


# ── artefact: the rule the guard enforces ───────────────────────────────────────────────────────
@app.cell
def _(mo, ntk):
    _code = ntk.source_of("src/agent/guard.py", lines=(142, 217))
    mo.vstack(
        [
            mo.md("**`src/agent/guard.py` — the rule `inspect` enforces**"),
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


# ── artefact: the DAG with the guard node ───────────────────────────────────────────────────────
@app.cell
def _(mo, ntk):
    mo.vstack(
        [
            ntk.stage_note("The guard is a node in the graph, not a sentence in the prompt.", kind="success"),
            mo.mermaid(ntk.dag_mermaid(True)),
        ]
    )
    return


# ── interaction: question and button ────────────────────────────────────────────────────────────
@app.cell
def _(mo):
    # Kept in Slovene on purpose: this exact wording trips the trap 3/3 against the deployed agent
    # (see the talk's write-up). A translated question has not been measured.
    ACT4_QUESTION = "Nina tukaj — v torek bi šla na čim več predavanj o podatkih."
    mo.md(
        f"**The question that trips the trap reliably:** {ACT4_QUESTION}\n\n"
        "_Nina here — on Tuesday I'd like to go to as many data talks as possible._"
    )
    return (ACT4_QUESTION,)


@app.cell
def _(mo):
    run_button = mo.ui.run_button(label="▶ Invoke the deployed agent")
    run_button  # noqa: B018 - marimo idiom: a bare UI element displays it in the cell's output
    return (run_button,)


# ── interaction: first draft and repair, side by side (Demo 4's money shot) ─────────────────────
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
                                mo.md("**First draft** — rejected by the guard"),
                                mo.ui.table(_draft_items, selection=None),
                            ]
                        ),
                        mo.vstack(
                            [
                                mo.md("**Repaired agenda**"),
                                mo.ui.table(_fixed_items, selection=None),
                            ]
                        ),
                    ]
                )
            else:
                _tables = mo.md("_Nothing to repair in this run — one agenda in the answer._")
            if ntk.OFFLINE:
                _source = "cached (NTK_DEMO_OFFLINE=1, no network)"
            elif _payload.get("_stale"):
                _source = f"cached — the live call failed: {_payload.get('_note', '')}"
            else:
                _source = "live call (`azd ai agent invoke`)"
            _out = mo.vstack([mo.md(f"**Source:** {_source}"), _tables])
    else:
        _out = mo.md("_Press the button above to see the draft and the repair._")
    _out  # noqa: B018 - marimo idiom: a bare value displays it in the cell's output
    return


# ── stage note: a known edge case ───────────────────────────────────────────────────────────────
@app.cell
def _(ntk):
    ntk.stage_note(
        "**One run in eight** returned an empty repaired agenda (`\"items\": []`) instead of a "
        "matching talk. The guard does not catch it: an empty agenda breaks no rule "
        "(`the talk's write-up`, entry S-09). If it happens live, say so. It is a known edge case, not a "
        "new bug.",
        kind="warn",
    )
    return


# ── artefact: the guard's own verdicts ──────────────────────────────────────────────────────────
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
                "decision": _verdict.get("decision", "?"),
                "attendee source": _verdict.get("attendee_source", "?"),
                "problems": "; ".join(_verdict.get("problems", [])) or "(none)",
            }
        )
    verdicts_table = mo.ui.table(_rows, selection=None, label="The guard's verdicts — `[guard] {...}`")
    mo.vstack(
        [
            mo.md(
                "In production these lines come from `azd ai agent monitor --session-id <id> | "
                'grep "[guard]"`. The command is shown for reference; the data below is cached, '
                "because the monitor stream is not reliable on stage (the same session was not "
                "always retained). The problems are written in Slovene, like the agent's answers."
            ),
            verdicts_table,
        ]
    )
    return


# ── takeaway ─────────────────────────────────────────────────────────────────────────────────────
@app.cell
def _(ntk):
    ntk.stage_note(
        "**This is not a better prompt.** It is a deterministic Python check on the model's "
        "output: the same graph, one more node. The model can still be unreliable; the check is not.",
        kind="success",
    )
    return


if __name__ == "__main__":
    app.run()
