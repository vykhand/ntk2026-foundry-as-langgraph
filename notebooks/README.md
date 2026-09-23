# Demo notebooks — NTK 2026, Talk 2

Four Marimo notebooks are the primary stage surface for the four demo acts (one notebook per act). Each notebook is reactive: change a widget and every cell that
depends on it re-runs, so the speaker explains the code on one side and shows the consequence on
the other without retyping anything. `scripts/act1.py` / `act3.py` do the same two things from a terminal, if you would rather read a script than a notebook.

The notebooks are in **English**, the language of the talk. The Slovene edition of all four is kept
in `notebooks/sl/` — same cells, same code, same house module (`notebooks/_ntk.py`; each Slovene copy
puts `notebooks/` on its path in one line). The agent itself still answers in Slovene: its system
prompt says so, and changing that is a redeploy, not a notebook edit.

| Notebook | Act | What the room sees |
| --- | --- | --- |
| `01_graph.py` | 1 — The agent is a graph | three tools, the graph source, the **live DAG** growing a `guard` node when a switch flips, a question answered against the local hosted server |
| `02_deploy.py` | 2 — Publishing with one command | the 14-line hosting wrapper, `langgraph.json`, what `azd deploy` does, the immutable version list |
| `03_traces.py` | 3 — Traces and sandboxes | two invocations in two sessions that cannot see each other, and one call's spans as a waterfall |
| `04_guard.py` | 4 — The agent catches itself | the fake win (same prompt, three runs), the guard node, the deployed agent drafting a bad agenda and repairing it |

All four exist and share the house style set out below.

`pyproject.toml` sets `[tool.marimo.runtime] auto_instantiate = true` / `on_cell_change =
"autorun"`. Without it marimo opens these notebooks with every cell stale and nothing run, which
is not what you want on stage with a room watching — and it is what made the first pass of the
recordings capture four notebooks that had never executed. It also sets `[tool.marimo.save]
autosave = "off"` / `format_on_save = false`, because marimo normalises a file it saves: it strips
the section comments between cells and drops the `ntk` parameter from any cell whose body never
names it, which is exactly the dependency declaration the house style below asks for. Opening a
notebook must not rewrite it; save deliberately, and review the diff.

## Running them on stage

```bash
uv run marimo edit notebooks/            # opens the notebook browser — pick one, present it
uv run marimo edit notebooks/01_graph.py # or open a single notebook directly
```

`marimo edit` is what you run live: it's the interactive, editable server the room sees. Every
notebook also runs headless (`uv run python notebooks/01_graph.py`) for CI/rehearsal, and exports
to a static page (`uv run marimo export html notebooks/01_graph.py -o out.html`) if you ever need
a non-interactive fallback capture.

### The offline switch

```bash
NTK_DEMO_OFFLINE=1 uv run marimo edit notebooks/
```

Set `NTK_DEMO_OFFLINE=1` (any of `1`/`true`/`yes`/`on`) and every notebook answers from
`notebooks/cache/*.json` instead of touching the network or the local hosted server — this is
what you flip the moment the conference wi-fi dies, mid-talk, without restarting anything. Each
notebook shows a visible banner when it's running this way, so the room knows the answer is
cached and the speaker knows to say so.

`tests/test_notebooks.py` runs the whole suite with `NTK_DEMO_OFFLINE=1` and no network — that is
the contract every notebook is held to.

## House rules (all four notebooks)

These come straight from `BRIEF.md` and apply to every notebook, not just `01_graph.py`:

1. **Never runs `azd deploy`** or anything that writes to Azure. Read-only Azure calls are fine
   but a notebook should prefer not to need them; `02_deploy.py` narrates the deploy, it doesn't
   run one.
2. **No secrets on screen.** A notebook may `load_dotenv()` but must never render a token,
   subscription id or endpoint key — not even truncated. If a cell needs an env var's *presence*,
   show a boolean/redacted indicator, never the value.
3. **Nothing hangs if the network is down.** The only place a notebook touches the network is
   through `_ntk.cached(key, fn)`, which has a hard timeout and always falls back to the cache
   file (or a visible error) rather than blocking a cell forever.
4. **Fixture talk ids are positional and shift on every programme refresh** — never hard-code
   `t-074`-style ids in a notebook. Look talks up by day/track/time, same as the slides do.
5. **No eval scores, no statistics, no variance numbers** anywhere except `04_guard.py`, where the
   variance chart is the point.
6. **`src/agent` imports no Foundry/Azure code** (`tests/test_purity.py` enforces it). Notebooks
   themselves are not under `src/`, so a notebook *may* import `hosting` — keep that clearly on
   the Foundry side of the story (e.g. "here's the wrapper", never blurring it into `agent`).

## House style (for whoever writes `02_deploy.py`, `03_traces.py`, `04_guard.py`)

Copy this shape — it's what makes four notebooks read as one demo instead of four different ones.

**Cell order, always:** title → framing → the artefact → the interaction → the takeaway.
Concretely, in `01_graph.py`: title banner, a one-paragraph framing note, then the artefacts
(tools table, graph source, the guard switch + live DAG), then the interaction (question editor,
run button, the answer), then the closing takeaway (the purity point). Keep that shape; only the
artefact/interaction content changes per act.

**Language:** on-screen text (titles, `mo.md`, table labels, callouts) is in **English** — the talk
is given in English. `notebooks/sl/` holds the Slovene edition; a change to one notebook is made in
both. Where the two differ in what they cache (the questions they ask), the Slovene copy uses its
own `-sl` cache key. Code and code comments are in English in both.

**Tone:** plain statements. Say what is on screen and what it shows; no rhetorical questions, no
"money shot" language in anything the room reads.

**Every cell is small enough to read projected.** Prefer one artefact per cell over combining
several. `mo.ui.code_editor(..., max_height=...)` for source code (it scrolls internally, so it
never grows past a sane on-screen height); `ntk.source_of(path, lines=(start, end))` to show only
the relevant slice of a file, not the whole thing.

**Shared code lives in `_ntk.py`, not copy-pasted into each notebook.** In particular:

- `import _ntk as ntk` as its own cell, right after the `import marimo as mo` cell. Every cell
  that imports from `agent`, `hosting` or `scripts` takes `ntk` as a parameter (even if the body
  never uses it) — that's what tells marimo's dataflow graph the sys.path setup must run first.
  Don't rely on file order alone for that; declare the dependency.
- `ntk.OFFLINE` / `ntk.cached(key, fn)` for anything that touches the network or a local server.
  Give each notebook's cached answer(s) a distinct key (`"act1"`, `"act2-versions"`, …) — one
  `notebooks/cache/<key>.json` per thing that can be cached, not one big shared file.
  `cached()`'s `fn` should return exactly the dict the notebook displays; don't stash extra
  derived fields in the cache that the notebook recomputes anyway (`01_graph.py` recomputes the
  resolved agenda from the cached answer text on every run — the cache only holds what the live
  call itself would return).
- `ntk.dag_mermaid(enforce_constraints)` for any live LangGraph DAG — never hand-roll mermaid.
- `ntk.banner(title, subtitle)` for the title cell, `ntk.stage_note(text, kind=...)` for any
  callout, `ntk.offline_note()` (`ntk.offline_note("sl")` in the Slovene copies) for the "running
  from cache" banner.

**Displaying a `mo.ui.*` element or a computed value as a cell's output** is the one place ruff's
`B018` ("useless expression") disagrees with marimo's own idiom (a bare name as the last statement
in a cell *is* how you show it). `01_graph.py` marks each of these with
`# noqa: B018 - marimo idiom: a bare UI element displays it in the cell's output` — do the same
rather than silencing the whole file, and rather than wrapping every element in an unnecessary
`mo.vstack([...])` just to dodge the linter.

**Nothing that can hang.** No live network or subprocess call outside `ntk.cached()`. A
`mo.ui.run_button` gates any call that would otherwise fire on every reactive re-run (e.g. every
keystroke in a text area) — check `run_button.value` before calling out, and always let
`ntk.OFFLINE` bypass the button so a headless offline run has something real to show without a
click.

## Refreshing the cache

**After every `azd deploy`, run `uv run warm-cache`.** The Act 2 version table is fetched live
with a deliberately short timeout — a stage demo cannot afford a cell that hangs, and acquiring a
credential from cold takes longer than that — so the notebook quietly falls back to the cache and
the table stays a version or two behind. It showed v6 for two deploys. `warm-cache` runs the same
call through the same cache with no clock on it.

Cached answers also go stale as the programme refreshes (talk ids and times shift) or as prompts
change. To regenerate `notebooks/cache/act1.json`, run the local hosted server once with a real
model and let the notebook's own live path repopulate it:

```bash
LLM_PROVIDER=ollama LLM_REASONING_EFFORT=low PORT=8088 uv run python -m hosting.serve &
uv run marimo edit notebooks/01_graph.py   # NTK_DEMO_OFFLINE unset — click "▶ Ask the agent"
```

Clicking the run button with the server up calls it for real and overwrites the cache file with
the fresh answer; kill the background server afterwards. Do the equivalent for whichever cache
key a later notebook owns — the mechanism is the same `ntk.cached(key, fn)` call, it just needs
`NTK_DEMO_OFFLINE` unset and something real to call.

Never hand-edit a cache file's `answer` text to "fix" a bad model output for the stage — that's a
prompt or fixture problem, not a cache problem, and it would make the cached demo diverge from
what a live run actually produces.
