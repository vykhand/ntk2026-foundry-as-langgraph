"""House module for the NTK 2026 Talk 2 demo notebooks — shared, not a notebook itself.

Every ``notebooks/0N_*.py`` file imports this as a plain sibling module (``import _ntk as ntk``);
marimo puts the notebook's own directory on ``sys.path``, so the import needs no package plumbing.
The Slovene copies in ``notebooks/sl/`` put ``notebooks/`` on the path themselves, one line, and
share everything here — including the cache, under their own ``-sl`` keys where the text differs.

What lives here, and why it is here rather than in each notebook:

* **sys.path setup** — ``src/`` (for ``agent`` and ``hosting``) and the repo root (for ``scripts``)
  are not on the path for a script run as ``python notebooks/01_graph.py``; only pytest gets that
  for free (``pyproject.toml``'s ``[tool.pytest.ini_options] pythonpath``). This module fixes that
  once, at import time, before any notebook imports ``agent.graph`` or ``scripts.act1``.
* **OFFLINE + cached()** — the one mechanism that makes every demo safe when the room's wi-fi dies:
  flip ``NTK_DEMO_OFFLINE=1`` and every notebook answers from ``notebooks/cache/*.json`` instead of
  calling a local server or the network. ``tests/test_notebooks.py`` runs the whole suite this way.
* **StubChatModel** — lets a notebook draw the *real* compiled LangGraph graph
  (``agent.graph.build_graph``) without a real model, an API key, or a network call. The DAG on
  screen is the DAG the deployed agent runs; only the model that would fill in the assistant node
  is fake, and no notebook ever asks it to actually answer anything.
* **source_of / banner / stage_note** — small presentation helpers so the four notebooks look and
  read as one thing instead of four.

House rule this module exists to enforce: **nothing in here, or in a notebook that uses it, may
hang if the network is down.** ``cached()`` is the one place a notebook cell touches the network,
and it always has a cache fallback and a timeout.
"""

from __future__ import annotations

import json
import sys
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

# ── repo root resolution + sys.path setup ────────────────────────────────────────────────────
# This file is notebooks/_ntk.py, so the repo root is its parent's parent.
ROOT = Path(__file__).resolve().parents[1]
NOTEBOOKS_DIR = ROOT / "notebooks"
CACHE_DIR = NOTEBOOKS_DIR / "cache"

for _p in (str(ROOT), str(ROOT / "src")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

# Deliberately *after* the sys.path setup above — these come from src/agent and src/scripts-adjacent
# packages that only import cleanly once ROOT and ROOT/src are on the path.
import os  # noqa: E402

from langchain_core.language_models import BaseChatModel  # noqa: E402
from langchain_core.messages import AIMessage  # noqa: E402
from langchain_core.outputs import ChatGeneration, ChatResult  # noqa: E402

# ── offline switch ────────────────────────────────────────────────────────────────────────────
_TRUTHY = {"1", "true", "yes", "on"}
OFFLINE = os.environ.get("NTK_DEMO_OFFLINE", "").strip().lower() in _TRUTHY

# The cap for a call to the local server on :8088. gpt-oss:20b on this laptop needs ~20 s for the
# English questions (measured 2026-09-23), so the default 12 s cap showed the cache on stage.
LOCAL_MODEL_TIMEOUT = 60.0


def cache_path(key: str) -> Path:
    return CACHE_DIR / f"{key}.json"


def cached(key: str, fn: Callable[[], Any], *, timeout: float = 12.0) -> Any:
    """Return cached JSON for *key*, or call *fn* and refresh the cache.

    - ``OFFLINE`` (``NTK_DEMO_OFFLINE`` set truthy): never calls *fn* — reads
      ``notebooks/cache/<key>.json`` straight away. This is the path the conference wi-fi outage
      takes, and the only path ``tests/test_notebooks.py`` is allowed to exercise.
    - otherwise: calls *fn* with a hard timeout (a stage demo cannot afford a cell that hangs).
      On success the result is written back to the cache file, so the next offline run is fresh.
      On failure (exception *or* timeout) it falls back to whatever is already cached, and failing
      that, returns an ``{"error": ...}`` payload — a cell may show a stale or missing answer, but
      it never raises and never blocks.
    """
    path = cache_path(key)
    if OFFLINE:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
        return {"error": f"no cache for {key!r} and NTK_DEMO_OFFLINE is set"}

    from concurrent.futures import ThreadPoolExecutor
    from concurrent.futures import TimeoutError as FutureTimeoutError

    # The fallback recorder raises this (NTK_LIVE_TIMEOUT) so a recorded take shows a live answer
    # from a local model that needs ~11 s; on stage it is unset and the per-call timeout stands.
    timeout = float(os.environ.get("NTK_LIVE_TIMEOUT") or timeout)

    # Not `with ThreadPoolExecutor(...)`: its __exit__ joins the worker, so a call that overran the
    # timeout still held the cell until it finished — the timeout returned nothing early at all.
    # shutdown(wait=False) lets the cell show the cached answer now; the straggler ends on its own.
    pool = ThreadPoolExecutor(max_workers=1)
    future = pool.submit(fn)
    try:
        result = future.result(timeout=timeout)
    except FutureTimeoutError:
        stale = _read_cache_or_none(path)
        if stale is not None:
            return {**stale, "_stale": True, "_note": f"timed out after {timeout:.0f}s"}
        return {"error": f"{key} timed out after {timeout:.0f}s and no cache exists"}
    except Exception as exc:  # noqa: BLE001 - a stage demo must not crash on a network hiccup
        stale = _read_cache_or_none(path)
        if stale is not None:
            return {**stale, "_stale": True, "_note": f"live call failed: {exc}"}
        return {"error": f"{key} failed ({exc}) and no cache exists"}
    finally:
        pool.shutdown(wait=False)

    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return result


def _read_cache_or_none(path: Path) -> dict | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


# ── a model stand-in, only so a graph can be compiled and drawn ──────────────────────────────
class StubChatModel(BaseChatModel):
    """Never actually answers — just enough for ``build_graph`` to compile and to draw the DAG.

    Same shape as ``tests/test_graph.py::ScriptedToolModel``, minus the scripting: this one always
    returns a single empty ``AIMessage``, because no notebook cell that uses it ever calls
    ``.invoke``/``.ainvoke`` for real — it exists only so ``StateGraph.compile()`` has a
    ``BaseChatModel`` to bind tools to before ``.get_graph().draw_mermaid()`` runs.
    """

    @property
    def _llm_type(self) -> str:
        return "ntk-stub"

    def bind_tools(self, tools, **kwargs):  # type: ignore[override]
        return self

    def _generate(self, messages, stop=None, run_manager=None, **kwargs) -> ChatResult:
        return ChatResult(generations=[ChatGeneration(message=AIMessage(content=""))])


def dag_mermaid(enforce_constraints: bool) -> str:
    """The live DAG, as mermaid — the same object ``build_graph`` compiles for the real agent."""
    from agent.graph import build_graph

    graph = build_graph(StubChatModel(), enforce_constraints=enforce_constraints)
    return graph.get_graph().draw_mermaid()


def all_agendas(text: str) -> list[dict[str, Any]]:
    """Every JSON object in *text* that has an ``items`` list, in the order they appear.

    ``agent.contract.extract_agenda`` deliberately returns only the **last** one — the guard's
    repair, never the draft it rejected (see that function's own docstring: a turn the guard sent
    back for correction carries both agendas in its text, draft first). ``04_guard.py``'s money
    shot wants both, side by side, so this is the same scan without the "keep only the last" step.
    """
    from agent.contract import _candidate_objects

    return [
        obj
        for obj in _candidate_objects(text)
        if isinstance(obj, dict) and isinstance(obj.get("items"), list)
    ]


# ── showing code ──────────────────────────────────────────────────────────────────────────────
def source_of(path: str | Path, lines: tuple[int, int] | None = None) -> str:
    """The text of *path* (repo-root-relative or absolute), optionally a 1-indexed inclusive range.

    ``lines=(12, 40)`` returns lines 12 through 40 (both included) — the same convention as
    ``sed -n '12,40p'``.
    """
    p = Path(path)
    if not p.is_absolute():
        p = ROOT / p
    text = p.read_text(encoding="utf-8")
    if lines is None:
        return text
    start, end = lines
    all_lines = text.splitlines()
    return "\n".join(all_lines[max(start - 1, 0) : end])


# ── presentation helpers every notebook uses the same way ────────────────────────────────────
def banner(title: str, subtitle: str = ""):
    """The title cell every notebook opens with — one look, four notebooks."""
    import marimo as mo

    sub = f"\n\n{subtitle}" if subtitle else ""
    return mo.md(f"# {title}{sub}")


def stage_note(text: str, kind: str = "info"):
    """A small boxed callout for asides to the speaker or the room — same look everywhere.

    ``kind``: one of marimo's callout kinds (``"info"``, ``"success"``, ``"warn"``, ``"danger"``,
    ``"neutral"``). Use ``"warn"``/``"danger"`` only for real stage risk (offline mode, a slow
    network call); ``"success"`` for the closing takeaway.
    """
    import marimo as mo

    return mo.callout(mo.md(text), kind=kind)


_OFFLINE_NOTE = {
    "en": "**Offline** — `NTK_DEMO_OFFLINE=1` is set. This notebook shows cached answers "
    "(`notebooks/cache/*.json`) and calls no server.",
    "sl": "**Brez omrežja** — `NTK_DEMO_OFFLINE=1` je nastavljen, zvezek prikazuje predpomnjene "
    "odgovore (`notebooks/cache/*.json`), ne kliče lokalnega strežnika.",
}


def offline_note(lang: str = "en"):
    """The one line every notebook shows when it is serving cached answers, not live ones."""
    if not OFFLINE:
        return None
    return stage_note(_OFFLINE_NOTE[lang], kind="warn")


def now_seconds() -> float:
    """``time.monotonic()`` re-exported so notebooks don't each import ``time`` for one timer."""
    return time.monotonic()


__all__ = [
    "CACHE_DIR",
    "OFFLINE",
    "ROOT",
    "StubChatModel",
    "all_agendas",
    "banner",
    "cache_path",
    "cached",
    "dag_mermaid",
    "now_seconds",
    "offline_note",
    "source_of",
    "stage_note",
]
