"""The four demos are Marimo notebooks now, not terminal scripts — these tests catch what would
embarrass the speaker on stage: a notebook that doesn't even parse, one that grew back its own
private copy of `_ntk.py`'s helpers instead of sharing them, a hardcoded secret sitting in a file
that gets projected on a screen, or a cell that raises the moment the room's wi-fi dies.

`notebooks/_ntk.py` itself is a house module, not a notebook (see its own docstring) — it is the
thing every test below checks the *other* files import rather than duplicate, so it is excluded
from the notebooks these tests parametrize over.
"""

from __future__ import annotations

import ast
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
NOTEBOOKS_DIR = ROOT / "notebooks"

# The English notebooks are the stage set; notebooks/sl/ keeps the Slovene edition. Both are held
# to the same contract, so the copy that is not on stage cannot quietly rot.
NOTEBOOKS = sorted(
    p
    for pattern in ("*.py", "sl/*.py")
    for p in NOTEBOOKS_DIR.glob(pattern)
    if p.name != "_ntk.py" and not p.name.startswith("_")
)

pytestmark = pytest.mark.skipif(not NOTEBOOKS, reason="notebooks/ has no notebooks yet")

# A hardcoded secret looks like one of these: an opaque, high-entropy string nobody typed by hand —
# a vendor-prefixed API key, or any other long quoted run of base64/hex-ish characters. `.env`
# (Telegram bot token, Azure ids — see BRIEF.md's "no secrets" rule) is the only place a real value
# lives; a notebook may `load_dotenv()` it but must never embed or render one.
_TOKEN_PATTERN = re.compile(
    r"""
    sk-[A-Za-z0-9]{20,}                 # OpenAI-style secret key
    | gh[pousr]_[A-Za-z0-9]{20,}        # GitHub token
    | xox[baprs]-[A-Za-z0-9-]{10,}      # Slack token
    | AKIA[0-9A-Z]{12,}                 # AWS access key id
    | \d{6,}:[A-Za-z0-9_-]{30,}         # Telegram bot token shape (<id>:<secret>)
    | ['"][A-Za-z0-9+/_-]{32,}['"]      # any other long opaque quoted string
    """,
    re.VERBOSE,
)


def _source(path: Path) -> str:
    return path.read_text(encoding="utf-8")


@pytest.fixture(params=NOTEBOOKS, ids=lambda p: str(p.relative_to(NOTEBOOKS_DIR)))
def notebook(request) -> Path:
    return request.param


def test_notebook_parses_as_python(notebook):
    ast.parse(_source(notebook), filename=str(notebook))


def test_notebook_is_a_marimo_app(notebook):
    text = _source(notebook)
    assert "import marimo" in text, f"{notebook.name}: does not import marimo"
    assert re.search(r"\bapp\s*=\s*marimo\.App\(", text), f"{notebook.name}: no marimo.App(...)"
    assert "__generated_with" in text, f"{notebook.name}: missing marimo's __generated_with marker"


def test_notebook_imports_ntk_instead_of_duplicating_its_helpers(notebook):
    """Every notebook shares one house module (`notebooks/_ntk.py`) for the offline switch, the
    stub model, the DAG renderer and the presentation helpers — see that module's own docstring.
    A notebook that redefines one of these instead of importing it is a copy that can drift."""
    text = _source(notebook)
    assert re.search(r"^\s*import _ntk\b", text, re.MULTILINE), (
        f"{notebook.name}: does not `import _ntk` (notebooks/_ntk.py)"
    )
    duplicated = [
        needle
        for needle in (
            "class StubChatModel",
            "def cached(",
            "def dag_mermaid(",
            "def source_of(",
            "def all_agendas(",
        )
        if needle in text
    ]
    assert duplicated == [], f"{notebook.name}: redefines {duplicated} instead of importing _ntk"


def test_notebook_has_no_obvious_secret(notebook):
    offenders = [line.strip() for line in _source(notebook).splitlines() if _TOKEN_PATTERN.search(line)]
    assert offenders == [], f"{notebook.name}: looks like it embeds a secret — {offenders}"


@pytest.mark.slow
def test_notebook_runs_headless_offline(notebook, tmp_path):
    """The valuable, slow-ish check: does the whole notebook actually execute with the network
    switched off?

    `marimo export html` runs every cell in topological order and exits non-zero the moment one
    raises — the same signal an assertion gives, just for a notebook instead of a test function.
    `NTK_DEMO_OFFLINE=1` is the wi-fi-death path every notebook must survive (`notebooks/_ntk.py`'s
    `cached()`); it is what running this exact command on the conference network, unplugged, would
    look like. Run as a subprocess (not in-process) so one notebook's import side effects — or a
    hang — can never take the rest of the suite down with it, and marked `slow` so it can be
    deselected with `-m "not slow"` when iterating on something else.
    """
    out = tmp_path / f"{notebook.stem}.html"
    env = {**os.environ, "NTK_DEMO_OFFLINE": "1"}
    cmd = [
        sys.executable,
        "-m",
        "marimo",
        "export",
        "html",
        str(notebook),
        "-o",
        str(out),
        "--no-include-code",
    ]
    try:
        result = subprocess.run(cmd, cwd=ROOT, env=env, capture_output=True, text=True, timeout=120)
    except subprocess.TimeoutExpired as exc:
        pytest.fail(f"{notebook.name} did not finish within {exc.timeout:.0f}s offline — looks like a hang")
    assert result.returncode == 0, (
        f"{notebook.name} failed to run headless with NTK_DEMO_OFFLINE=1:\n"
        f"--- stdout ---\n{result.stdout}\n--- stderr ---\n{result.stderr}"
    )
