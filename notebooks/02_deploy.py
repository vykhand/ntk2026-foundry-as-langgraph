import marimo

__generated_with = "0.24.2"
app = marimo.App(width="medium", app_title="Demo 2 · Publishing with one command")


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
            "Demo 2 · Publishing with one command",
            "The graph from Demo 1, plus a wrapper that Foundry hosts.",
        )
    ]
    _offline = ntk.offline_note()
    if _offline is not None:
        _pieces.append(_offline)
    mo.vstack(_pieces)
    return


# ── framing ───────────────────────────────────────────────────────────────────────────────────────
@app.cell
def _(mo):
    mo.md(r"""
    The graph does not change from here on. Two files are added: a thin wrapper and a small
    manifest that tells the platform where the graph is.

    Order: the wrapper and the manifest, what `azd deploy` does, then versions and rollback.
    Every deploy creates a new immutable version. Rollback is one command.
    """)
    return


# ── artefact: the whole Foundry surface ──────────────────────────────────────────────────────────
@app.cell
def _(mo, ntk):
    _code = ntk.source_of("src/hosting/serve.py")
    mo.vstack(
        [
            mo.md("**`src/hosting/serve.py` — the entire Foundry integration. 14 lines.**"),
            mo.ui.code_editor(
                value=_code,
                language="python",
                disabled=True,
                max_height=240,
                show_copy_button=False,
            ),
        ]
    )
    return


# ── artefact: the manifest that says where the graph is ──────────────────────────────────────────
@app.cell
def _(mo, ntk):
    _code = ntk.source_of("langgraph.json")
    mo.vstack(
        [
            mo.md("**`langgraph.json` — tells the platform where the graph is.**"),
            mo.ui.code_editor(
                value=_code,
                language="json",
                disabled=True,
                max_height=100,
                show_copy_button=False,
            ),
        ]
    )
    return


# ── artefact: azure.yaml — entry point + environment ─────────────────────────────────────────────
@app.cell
def _(mo, ntk):
    _code = ntk.source_of("azure.yaml", lines=(39, 77))
    mo.vstack(
        [
            mo.md(
                "**`azure.yaml`, service `ntk-asistent`** — entry point and environment "
                "variables. Every change here creates a new version."
            ),
            mo.ui.code_editor(
                value=_code,
                language="yaml",
                disabled=True,
                max_height=420,
                show_copy_button=False,
            ),
        ]
    )
    return


# ── artefact: what 'azd deploy' does (never run from here) ──────────────────────────────────────
@app.cell
def _(mo, ntk):
    _steps = [
        "`azd deploy` zips the repo, filtered by `.agentignore`: `src/`, `prompts/`, the manifest.",
        "The ZIP goes to a remote build on the platform, not on the laptop.",
        "The build produces a new, **immutable** agent version.",
        "The version is activated: environment variables are registered, the endpoint serves it.",
    ]
    _numbered = "\n".join(f"{i}. {s}" for i, s in enumerate(_steps, start=1))
    mo.vstack(
        [
            mo.md(
                "**What `azd deploy` does.** The speaker runs it in a terminal; this notebook "
                "does not:"
            ),
            mo.md("```bash\nazd deploy\n```"),
            mo.md(_numbered),
            ntk.stage_note(
                "If the network fails on stage: "
                "see the versions in the portal — the same command, its result.",
                kind="warn",
            ),
        ]
    )
    return


# ── artefact: the live immutable versions ────────────────────────────────────────────────────────
@app.cell
def _(mo, ntk):
    from scripts.rollback import version_payload

    # The live call lives in scripts/rollback.py so the version table on stage and the one
    # `uv run rollback --list` prints cannot disagree. Short timeout on purpose: a dead network
    # degrades to the cache file instead of hanging a stage demo. `uv run warm-cache` fills that
    # cache off the stage clock, which is the only way it keeps up with a fresh deploy.
    versions_payload = ntk.cached("act2-versions", version_payload, timeout=6.0)

    def _traffic(pct):
        return "—" if pct is None else f"{pct} %"

    _rows = [
        {
            "version": f"v{row['version']}",
            "status": row["status"],
            "created": row["created_at"],
            "traffic": _traffic(row.get("traffic_percentage")),
        }
        for row in versions_payload.get("versions", [])
    ]
    versions_table = mo.ui.table(
        _rows,
        selection=None,
        label=f"Immutable versions — agent {versions_payload.get('agent_name', '?')}",
    )
    versions_table  # noqa: B018 - marimo idiom: a bare UI element displays it in the cell's output
    return (versions_payload,)


# ── interaction: pick a version ──────────────────────────────────────────────────────────────────
@app.cell
def _(mo, versions_payload):
    _rows = versions_payload.get("versions", [])
    _options = [row["version"] for row in _rows] or ["1"]
    _current = next((row["version"] for row in _rows if row.get("traffic_percentage")), None)
    _default = next((v for v in _options if v != _current), _options[0])
    version_dropdown = mo.ui.dropdown(
        options=_options,
        value=_default,
        label="Route traffic to version",
    )
    version_dropdown  # noqa: B018 - marimo idiom: a bare UI element displays it in the cell's output
    return (version_dropdown,)


# ── interaction: the rollback command (text only, never run) ─────────────────────────────────────
@app.cell
def _(mo, ntk, version_dropdown):
    import json

    from scripts.rollback import selector_patch

    _version = version_dropdown.value
    _command = f"uv run rollback {_version}"
    _patch_json = json.dumps(selector_patch(_version), indent=2)
    mo.vstack(
        [
            ntk.stage_note(
                f"Command to route traffic to version **v{_version}**. Text for the terminal; "
                "this notebook never runs it.",
                kind="warn",
            ),
            mo.md(f"```bash\n{_command}\n```"),
            mo.md("**The single merge-patch this command sends** (`scripts.rollback.selector_patch`):"),
            mo.ui.code_editor(
                value=_patch_json,
                language="json",
                disabled=True,
                max_height=200,
                show_copy_button=False,
            ),
        ]
    )
    return


# ── takeaway: rollback is one function ──────────────────────────────────────────────────────────
@app.cell
def _(mo, ntk):
    _code = ntk.source_of("scripts/rollback.py", lines=(43, 63))
    mo.vstack(
        [
            ntk.stage_note(
                "**Rollback is one call**: `agents.update_details` with one merge-patch. No version "
                "is deleted, so a bad deploy is a command, not an incident.",
                kind="success",
            ),
            mo.ui.code_editor(
                value=_code,
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
