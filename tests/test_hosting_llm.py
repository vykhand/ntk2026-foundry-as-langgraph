"""The env-switchable model factory (no network: only object construction is tested)."""

from __future__ import annotations

import pytest

from hosting.llm import chat_model, deployment_name, describe, provider_name

CLEAR = (
    "LLM_PROVIDER",
    "FOUNDRY_PROJECT_ENDPOINT",
    "AZURE_AI_MODEL_DEPLOYMENT_NAME",
    "MICROSOFT_FOUNDRY_MODEL_DEPLOYMENT_NAME",
    "FOUNDRY_MODEL_NAME",
    "MODEL_DEPLOYMENT_NAME",
    "OLLAMA_MODEL",
    "OLLAMA_BASE_URL",
    "OPENAI_API_KEY",
    "OPENAI_BASE_URL",
    "OPENAI_MODEL",
)


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    for name in CLEAR:
        monkeypatch.delenv(name, raising=False)


def test_default_provider_is_ollama_without_a_project_endpoint():
    assert provider_name() == "ollama"


def test_project_endpoint_switches_default_to_foundry(monkeypatch):
    monkeypatch.setenv("FOUNDRY_PROJECT_ENDPOINT", "https://x.services.ai.azure.com/api/projects/p")
    assert provider_name() == "foundry"


def test_explicit_provider_wins(monkeypatch):
    monkeypatch.setenv("FOUNDRY_PROJECT_ENDPOINT", "https://x.services.ai.azure.com/api/projects/p")
    monkeypatch.setenv("LLM_PROVIDER", "ollama")
    assert provider_name() == "ollama"


def test_unknown_provider_raises(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "carrier-pigeon")
    with pytest.raises(ValueError, match="carrier-pigeon"):
        chat_model()


def test_ollama_model_uses_openai_compatible_endpoint(monkeypatch):
    monkeypatch.setenv("OLLAMA_MODEL", "qwen3:8b")
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://localhost:11434/v1")
    model = chat_model()
    assert model.model_name == "qwen3:8b"
    assert str(model.openai_api_base).rstrip("/") == "http://localhost:11434/v1"
    assert model.use_responses_api is not True  # Ollama's /v1/responses is non-stateful
    assert describe().startswith("ollama:qwen3:8b@")


@pytest.mark.parametrize(
    "name",
    [
        "AZURE_AI_MODEL_DEPLOYMENT_NAME",
        "MICROSOFT_FOUNDRY_MODEL_DEPLOYMENT_NAME",
        "FOUNDRY_MODEL_NAME",
        "MODEL_DEPLOYMENT_NAME",
    ],
)
def test_any_of_the_four_deployment_env_names_is_honoured(monkeypatch, name):
    monkeypatch.setenv(name, "gpt-5.4")
    assert deployment_name() == "gpt-5.4"


def test_deployment_name_prefers_the_sample_convention(monkeypatch):
    monkeypatch.setenv("FOUNDRY_MODEL_NAME", "wrong")
    monkeypatch.setenv("AZURE_AI_MODEL_DEPLOYMENT_NAME", "right")
    assert deployment_name() == "right"
    assert deployment_name.__module__ == "hosting.llm"


def test_default_deployment_matches_azure_yaml():
    import re
    from pathlib import Path

    text = (Path(__file__).resolve().parents[1] / "azure.yaml").read_text(encoding="utf-8")
    declared = re.search(r"deployments:\s*\n\s*- name: (\S+)", text).group(1)
    assert deployment_name() == declared
