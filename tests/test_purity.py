"""The stage claim, enforced: ``src/agent`` contains zero Foundry/Azure/provider code."""

from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
AGENT_DIR = ROOT / "src" / "agent"
FORBIDDEN_PREFIXES = (
    "azure",
    "langchain_azure_ai",
    "langchain_openai",
    "openai",
    "hosting",
    "azd",
    "microsoft",
)


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
    return names


def test_agent_package_has_no_foundry_or_provider_imports():
    offenders = {}
    for path in sorted(AGENT_DIR.glob("*.py")):
        bad = sorted(name for name in _imports(path) if name.split(".")[0] in FORBIDDEN_PREFIXES)
        if bad:
            offenders[path.name] = bad
    assert not offenders, f"Foundry/provider code leaked into src/agent: {offenders}"


def test_agent_package_only_speaks_langchain_and_stdlib():
    allowed_third_party = {"langchain_core", "langgraph"}
    for path in sorted(AGENT_DIR.glob("*.py")):
        for name in _imports(path):
            top = name.split(".")[0]
            if top in {"agent", "__future__"} or top in allowed_third_party:
                continue
            assert top in _STDLIB, f"{path.name} imports unexpected module {name!r}"


def test_hosting_wrapper_fits_on_one_slide():
    source = (ROOT / "src" / "hosting" / "serve.py").read_text(encoding="utf-8").splitlines()
    code_lines = [ln for ln in source if ln.strip() and not ln.strip().startswith(("#", '"""'))]
    assert len(code_lines) <= 12, f"serve.py grew to {len(code_lines)} lines; keep it slide-sized"


import sys  # noqa: E402

_STDLIB = set(sys.stdlib_module_names)
