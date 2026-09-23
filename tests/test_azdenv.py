"""The azd-environment fallback used by the cloud scripts."""

import json

from scripts import azdenv


def _repo(tmp_path, env_name="demo", values='FOUNDRY_PROJECT_ENDPOINT="https://x/api/projects/p"\n'):
    (tmp_path / ".azure" / env_name).mkdir(parents=True)
    (tmp_path / ".azure" / "config.json").write_text(
        json.dumps({"version": 1, "defaultEnvironment": env_name})
    )
    (tmp_path / ".azure" / env_name / ".env").write_text(values)
    return tmp_path


def test_default_environment_comes_from_config(tmp_path, monkeypatch):
    monkeypatch.delenv("AZURE_ENV_NAME", raising=False)
    assert azdenv.azd_env_name(_repo(tmp_path)) == "demo"


def test_explicit_env_name_wins(tmp_path, monkeypatch):
    monkeypatch.setenv("AZURE_ENV_NAME", "other")
    assert azdenv.azd_env_name(_repo(tmp_path)) == "other"


def test_missing_azure_dir_is_fine(tmp_path, monkeypatch):
    monkeypatch.delenv("AZURE_ENV_NAME", raising=False)
    assert azdenv.azd_env_name(tmp_path) is None
    assert azdenv.load_env(tmp_path) is None


def test_load_env_fills_only_unset_keys(tmp_path, monkeypatch):
    monkeypatch.delenv("AZURE_ENV_NAME", raising=False)
    monkeypatch.delenv("FOUNDRY_PROJECT_ENDPOINT", raising=False)
    monkeypatch.setenv("AZURE_LOCATION", "keep-me")
    root = _repo(
        tmp_path, values='FOUNDRY_PROJECT_ENDPOINT="https://x/api/projects/p"\nAZURE_LOCATION="westeurope"\n'
    )
    assert azdenv.load_env(root) == "demo"
    assert azdenv.load_env(root) == "demo"  # idempotent
    import os

    assert os.environ["FOUNDRY_PROJECT_ENDPOINT"] == "https://x/api/projects/p"  # quotes stripped
    assert os.environ["AZURE_LOCATION"] == "keep-me"  # the shell wins
