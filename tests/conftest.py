"""Shared pytest config for the whole suite — currently just marker registration.

Kept here rather than in ``pyproject.toml`` so ``tests/`` stays the one place that has to change
when the test suite grows a new kind of check.
"""

from __future__ import annotations


def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "slow: exercises a slow-ish, valuable path (deselect with `-m 'not slow'`)",
    )
