"""`notebooks/_ntk.py cached()` — the one path from a notebook cell to the network.

Its promise to the stage is that a slow call returns the cached answer *on time*. It used to return
it only once the slow call had finished anyway (`with ThreadPoolExecutor` joins its worker on exit),
which made the timeout decorative. No network here: the "call" is a local sleep."""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "notebooks"))

import _ntk as ntk  # noqa: E402


@pytest.fixture
def live(monkeypatch, tmp_path):
    monkeypatch.setattr(ntk, "OFFLINE", False)
    monkeypatch.setattr(ntk, "CACHE_DIR", tmp_path)
    monkeypatch.delenv("NTK_LIVE_TIMEOUT", raising=False)
    return tmp_path


def test_a_slow_call_falls_back_to_the_cache_on_time(live):
    (live / "k.json").write_text(json.dumps({"answer": "cached"}))
    start = time.monotonic()
    result = ntk.cached("k", lambda: time.sleep(3) or {"answer": "live"}, timeout=0.3)
    assert time.monotonic() - start < 1.5
    assert result["answer"] == "cached" and result["_stale"] is True


def test_a_fast_call_refreshes_the_cache(live):
    assert ntk.cached("k", lambda: {"answer": "live"}, timeout=5) == {"answer": "live"}
    assert json.loads((live / "k.json").read_text()) == {"answer": "live"}


def test_the_recorder_can_raise_the_timeout(live, monkeypatch):
    monkeypatch.setenv("NTK_LIVE_TIMEOUT", "5")
    result = ntk.cached("k", lambda: time.sleep(0.5) or {"answer": "live"}, timeout=0.1)
    assert result == {"answer": "live"}
