"""Fill the process environment from the repo ``.env`` and then the selected azd environment.

``azd provision`` writes ``FOUNDRY_PROJECT_ENDPOINT`` (and friends) into ``.azure/<env>/.env``;
the cloud scripts (``invoke``, ``rollback``) read it from there so nothing has to be exported
by hand. Values already present in the environment always win.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from dotenv import dotenv_values, load_dotenv

ROOT = Path(__file__).resolve().parents[1]


def azd_env_name(root: Path = ROOT) -> str | None:
    explicit = os.environ.get("AZURE_ENV_NAME", "").strip()
    if explicit:
        return explicit
    config = root / ".azure" / "config.json"
    try:
        return json.loads(config.read_text()).get("defaultEnvironment") or None
    except (OSError, ValueError):
        return None


def load_env(root: Path = ROOT) -> str | None:
    """Load ``.env`` (no override), then the azd environment's ``.env`` for anything still unset.

    Returns the azd environment name that was used, or ``None``.
    """
    load_dotenv(root / ".env")
    name = azd_env_name(root)
    if not name:
        return None
    values = dotenv_values(root / ".azure" / name / ".env")
    for key, value in values.items():
        if value is not None and not os.environ.get(key):
            os.environ[key] = value
    return name


__all__ = ["azd_env_name", "load_env"]
