"""Chat-model factory — the env-switchable seam between the agent and its model.

Providers (``LLM_PROVIDER``):

* ``foundry`` — the project's model deployment via the Foundry OpenAI-compatible
  endpoint with an Entra bearer token (this is the hosted-agent path; the
  platform injects ``FOUNDRY_PROJECT_ENDPOINT`` and ``AZURE_AI_MODEL_DEPLOYMENT_NAME``).
* ``ollama``  — a local model through Ollama's OpenAI-compatible API (Act 1, offline).
* ``openai``  — any OpenAI-compatible endpoint (``OPENAI_BASE_URL``/``OPENAI_API_KEY``).

Default: ``foundry`` when ``FOUNDRY_PROJECT_ENDPOINT`` is set, otherwise ``ollama``.
"""

from __future__ import annotations

import os

from langchain_core.language_models import BaseChatModel
from langchain_openai import ChatOpenAI

_AZURE_AI_SCOPE = "https://ai.azure.com/.default"
# Four names circulate in the docs/samples and none is platform-injected (the talk's write-up, D-11).
_DEPLOYMENT_ENV_VARS = (
    "AZURE_AI_MODEL_DEPLOYMENT_NAME",
    "MICROSOFT_FOUNDRY_MODEL_DEPLOYMENT_NAME",
    "FOUNDRY_MODEL_NAME",
    "MODEL_DEPLOYMENT_NAME",
)
_DEFAULT_DEPLOYMENT = "gpt-5.4-mini"


def deployment_name() -> str:
    for name in _DEPLOYMENT_ENV_VARS:
        value = os.environ.get(name, "").strip()
        if value:
            return value
    return _DEFAULT_DEPLOYMENT


def provider_name() -> str:
    explicit = os.environ.get("LLM_PROVIDER", "").strip().lower()
    if explicit:
        return explicit
    return "foundry" if os.environ.get("FOUNDRY_PROJECT_ENDPOINT") else "ollama"


def _foundry_model() -> ChatOpenAI:
    # Mirrors the official langgraph hosted-agent samples (foundry-samples, Sept 2026).
    from azure.ai.projects import AIProjectClient
    from azure.identity import DefaultAzureCredential, get_bearer_token_provider

    project_endpoint = os.environ["FOUNDRY_PROJECT_ENDPOINT"].rstrip("/")
    deployment = deployment_name()
    credential = DefaultAzureCredential()
    project = AIProjectClient(endpoint=project_endpoint, credential=credential)
    openai_client = project.get_openai_client()
    token_provider = get_bearer_token_provider(credential, _AZURE_AI_SCOPE)
    # Responses API so spans carry gen_ai.response.id (the portal trace view needs it).
    return ChatOpenAI(
        model=deployment,
        base_url=str(openai_client.base_url),
        api_key=token_provider,
        use_responses_api=True,
        output_version="responses/v1",
    )


def _ollama_model() -> ChatOpenAI:
    extra: dict = {}
    # gpt-oss / qwen3 reason before answering; "low" keeps a stage answer under a minute.
    effort = os.environ.get("LLM_REASONING_EFFORT", "").strip().lower()
    if effort:
        extra["reasoning_effort"] = effort
    return ChatOpenAI(
        model=os.environ.get("OLLAMA_MODEL", "gpt-oss:20b"),
        base_url=os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434/v1"),
        api_key="ollama",  # Ollama ignores the key but the client requires one
        temperature=float(os.environ.get("LLM_TEMPERATURE", "0")),
        timeout=float(os.environ.get("LLM_TIMEOUT_SECONDS", "180")),
        max_retries=1,
        **extra,
    )


def _openai_compatible_model() -> ChatOpenAI:
    return ChatOpenAI(
        model=os.environ.get("OPENAI_MODEL", "gpt-5-mini"),
        base_url=os.environ.get("OPENAI_BASE_URL") or None,
        api_key=os.environ.get("OPENAI_API_KEY"),
        temperature=float(os.environ.get("LLM_TEMPERATURE", "0")),
    )


def chat_model() -> BaseChatModel:
    provider = provider_name()
    if provider == "foundry":
        return _foundry_model()
    if provider == "ollama":
        return _ollama_model()
    if provider == "openai":
        return _openai_compatible_model()
    raise ValueError(f"unknown LLM_PROVIDER={provider!r}; use foundry, ollama or openai")


def describe() -> str:
    provider = provider_name()
    if provider == "foundry":
        return f"foundry:{deployment_name()}"
    if provider == "ollama":
        model = os.environ.get("OLLAMA_MODEL", "gpt-oss:20b")
        base = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434/v1")
        return f"ollama:{model}@{base}"
    return f"openai:{os.environ.get('OPENAI_MODEL', 'gpt-5-mini')}"


__all__ = ["chat_model", "deployment_name", "describe", "provider_name"]
