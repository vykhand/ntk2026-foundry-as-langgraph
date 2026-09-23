"""The graph the Foundry hosting entrypoint loads (``langgraph.json`` → ``app.py:graph``).

This file exists so that ``src/agent`` never has to know where its model comes
from. Hosted or local, the graph is the same object.
"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

from agent.graph import build_graph
from hosting.llm import chat_model, describe
from hosting.telemetry import quiet_local_telemetry

load_dotenv(Path(__file__).resolve().parents[2] / ".env")

# The one config switch the graph itself takes: NTK_ENFORCE_CONSTRAINTS turns on the guard node
# (agent.guard). Off by default so the deployed versions 1-3 keep their two-node shape.
_ENFORCE = os.environ.get("NTK_ENFORCE_CONSTRAINTS", "").strip().lower() in {"1", "true", "yes", "on"}

# One status line at import time (logging is not configured yet at this point).
print(
    f"ntk-asistent · model {describe()} · guard {'on' if _ENFORCE else 'off'} · {quiet_local_telemetry()}",
    file=sys.stderr,
    flush=True,
)

# The guard's verdicts go to stderr on their own handler rather than through the root logger:
# the hosting server configures logging after this module is imported, and whatever it decides
# about the root level should not silence the one thing we deploy the guard to be able to audit.
_guard_log = logging.getLogger("ntk.guard")
if not _guard_log.handlers:
    _handler = logging.StreamHandler(sys.stderr)
    _handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    _guard_log.addHandler(_handler)
    _guard_log.setLevel(logging.INFO)
    _guard_log.propagate = False  # the root logger prints the same line again otherwise

graph = build_graph(chat_model(), enforce_constraints=_ENFORCE)
