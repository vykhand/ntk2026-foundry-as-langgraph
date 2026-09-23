import marimo

__generated_with = "0.24.2"
app = marimo.App(width="medium", app_title="Demo 2 · Objava z enim ukazom")


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
            "Demo 2 · Objava z enim ukazom",
            "Isti graf iz Demota 1 — samo z ovojnico, ki jo gosti Foundry.",
        )
    ]
    _offline = ntk.offline_note("sl")
    if _offline is not None:
        _pieces.append(_offline)
    mo.vstack(_pieces)
    return


# ── framing ───────────────────────────────────────────────────────────────────────────────────────
@app.cell
def _(mo):
    mo.md(r"""
    Graf iz prejšnjega demota se od tod naprej ne spremeni niti za vrstico. Kar se doda, je tanka
    ovojnica in majhen manifest, ki platformi povesta, kje je graf.

    Najprej ta dva — ovojnica in manifest. Nato, kaj `azd deploy` dejansko naredi. Nazadnje
    varnostna mreža: vsaka objava je nova, nespremenljiva različica; nazaj grede je en ukaz.
    """)
    return


# ── artefact: cela stična ploskev s Foundryjem ────────────────────────────────────────────────────
@app.cell
def _(mo, ntk):
    _code = ntk.source_of("src/hosting/serve.py")
    mo.vstack(
        [
            mo.md("**`src/hosting/serve.py` — cela stična ploskev s Foundryjem. 14 vrstic.**"),
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


# ── artefact: manifest, ki pove, kje je graf ─────────────────────────────────────────────────────
@app.cell
def _(mo, ntk):
    _code = ntk.source_of("langgraph.json")
    mo.vstack(
        [
            mo.md("**`langgraph.json` — manifest, ki pove platformi, kje je graf.**"),
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


# ── artefact: azure.yaml — vstopna točka + okoljske spremenljivke ────────────────────────────────
@app.cell
def _(mo, ntk):
    _code = ntk.source_of("azure.yaml", lines=(39, 77))
    mo.vstack(
        [
            mo.md(
                "**`azure.yaml`, storitev `ntk-asistent`** — vstopna točka in okoljske "
                "spremenljivke; vsaka sprememba spodaj je nova različica."
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


# ── artefact: kaj naredi 'azd deploy' (nikoli izvedeno) ──────────────────────────────────────────
@app.cell
def _(mo, ntk):
    _steps = [
        "`azd deploy` repo stisne v ZIP (glede na `.agentignore` — samo `src/`, `prompts/`, manifest).",
        "ZIP odpotuje v oddaljeno gradnjo (remote build) na platformi, ne lokalno na prenosniku.",
        "Iz gradnje nastane nova, **nespremenljiva** različica agenta.",
        "Različica se aktivira — okoljske spremenljivke se registrirajo, endpoint jo prevzame.",
    ]
    _numbered = "\n".join(f"{i}. {s}" for i, s in enumerate(_steps, start=1))
    mo.vstack(
        [
            mo.md(
                "**Kaj naredi `azd deploy`** — ukaz, ki ga govorec vtipka v terminal; ta zvezek "
                "ga ne požene:"
            ),
            mo.md("```bash\nazd deploy\n```"),
            mo.md(_numbered),
            ntk.stage_note(
                "Če splet na odru odpove: poglejte različice v portalu — isti ukaz, njegov rezultat.",
                kind="warn",
            ),
        ]
    )
    return


# ── artefact: žive nespremenljive različice ──────────────────────────────────────────────────────
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
            "različica": f"v{row['version']}",
            "stanje": row["status"],
            "ustvarjeno": row["created_at"],
            "promet": _traffic(row.get("traffic_percentage")),
        }
        for row in versions_payload.get("versions", [])
    ]
    versions_table = mo.ui.table(
        _rows,
        selection=None,
        label=f"Nespremenljive različice — agent {versions_payload.get('agent_name', '?')}",
    )
    versions_table  # noqa: B018 - marimo idiom: a bare UI element displays it in the cell's output
    return (versions_payload,)


# ── interaction: izberite različico ──────────────────────────────────────────────────────────────
@app.cell
def _(mo, versions_payload):
    _rows = versions_payload.get("versions", [])
    _options = [row["version"] for row in _rows] or ["1"]
    _current = next((row["version"] for row in _rows if row.get("traffic_percentage")), None)
    _default = next((v for v in _options if v != _current), _options[0])
    version_dropdown = mo.ui.dropdown(
        options=_options,
        value=_default,
        label="Vrni promet na različico",
    )
    version_dropdown  # noqa: B018 - marimo idiom: a bare UI element displays it in the cell's output
    return (version_dropdown,)


# ── interaction: ukaz za vrnitev (samo besedilo, nikoli izvedeno) ────────────────────────────────
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
                f"Ukaz za preklop prometa na različico **v{_version}** — besedilo za terminal, "
                "ta zvezek ga nikoli ne izvede.",
                kind="warn",
            ),
            mo.md(f"```bash\n{_command}\n```"),
            mo.md("**En sam merge-patch, ki ga ta ukaz pošlje** (`scripts.rollback.selector_patch`):"),
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


# ── takeaway: vrnitev je ena funkcija ──────────────────────────────────────────────────────────
@app.cell
def _(mo, ntk):
    _code = ntk.source_of("scripts/rollback.py", lines=(43, 63))
    mo.vstack(
        [
            ntk.stage_note(
                "**Cela vrnitev prometa je en klic** — `agents.update_details` z enim samim "
                "merge-patchom. Nobena različica se ne izbriše, zato je 'oops' ukaz, ne incident.",
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
