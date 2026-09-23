"""Call the agent with the *plain* OpenAI SDK — the Act 2 beat.

Cloud (Phase 2):  ``uv run invoke "Sestavi mi urnik za torek …"``
    Targets ``{FOUNDRY_PROJECT_ENDPOINT}/agents/{AGENT_NAME}/endpoint/protocols/openai``
    with an Entra bearer token (``DefaultAzureCredential``, scope ``https://ai.azure.com/.default``).
    Endpoint shape per docs/ground-truth.md §6; verified against a live project in Phase 2.

Local (Act 1 cross-check): ``uv run invoke --local "…"``
    Same code, base_url ``http://127.0.0.1:8088`` — the hosting layer speaks the same contract.

Multi-turn: pass ``--previous-response-id`` (printed after every call).
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

from openai import OpenAI

from scripts.azdenv import load_env

ROOT = Path(__file__).resolve().parents[1]
ACT1_QUESTION = "Sestavi mi urnik za torek — zanima me AI in Azure, nič pred deveto, pusti mi luknjo za kavo."
_AZURE_AI_SCOPE = "https://ai.azure.com/.default"


def _cloud_client(agent_name: str) -> tuple[OpenAI, str]:
    from azure.identity import DefaultAzureCredential, get_bearer_token_provider

    endpoint = os.environ.get("FOUNDRY_PROJECT_ENDPOINT", "").rstrip("/")
    if not endpoint:
        sys.exit("FOUNDRY_PROJECT_ENDPOINT is not set (azd env get-values, or .env)")
    base_url = f"{endpoint}/agents/{agent_name}/endpoint/protocols/openai"
    token_provider = get_bearer_token_provider(DefaultAzureCredential(), _AZURE_AI_SCOPE)
    # The openai SDK accepts a callable api_key and calls it per request (token refresh for free).
    # The hosted endpoint rejects calls without `api-version` (verified 2026-09-05: HTTP 400
    # "Missing required query parameter: api-version"); `v1` is what `azd ai agent show` prints.
    api_version = os.environ.get("FOUNDRY_API_VERSION", "v1")
    return OpenAI(
        base_url=base_url, api_key=token_provider, default_query={"api-version": api_version}
    ), base_url


def _local_client(port: int) -> tuple[OpenAI, str]:
    base_url = f"http://127.0.0.1:{port}"
    return OpenAI(base_url=base_url, api_key="local"), base_url


def main(argv: list[str] | None = None) -> int:
    load_env(ROOT)
    parser = argparse.ArgumentParser(description="Invoke the NTK asistent through the OpenAI SDK")
    parser.add_argument("question", nargs="?", default=ACT1_QUESTION)
    parser.add_argument("--local", action="store_true", help="target the local host instead of Foundry")
    parser.add_argument("--port", type=int, default=int(os.environ.get("PORT", "8088")))
    parser.add_argument("--agent", default=os.environ.get("AGENT_NAME", "ntk-asistent"))
    parser.add_argument("--previous-response-id", default=None)
    parser.add_argument("--stream", action="store_true")
    parser.add_argument("--raw", action="store_true", help="dump the full response object")
    args = parser.parse_args(argv)

    client, base_url = _local_client(args.port) if args.local else _cloud_client(args.agent)
    print(f"→ {base_url}/responses")
    # The hosted endpoint validates the payload strictly: `previous_response_id: null` is a 400
    # ("Expected string, got Null"), so only send the field when there is a value.
    turn: dict = {"input": args.question}
    if args.previous_response_id:
        turn["previous_response_id"] = args.previous_response_id
    started = time.monotonic()
    if args.stream:
        text_parts: list[str] = []
        response_id = None
        with client.responses.stream(**turn) as stream:
            for event in stream:
                if event.type == "response.output_text.delta":
                    print(event.delta, end="", flush=True)
                    text_parts.append(event.delta)
                elif event.type == "response.created":
                    response_id = event.response.id
            print()
        elapsed = time.monotonic() - started
    else:
        response = client.responses.create(**turn)
        elapsed = time.monotonic() - started
        response_id = response.id
        if args.raw:
            print(response.model_dump_json(indent=2))
        else:
            calls = [item.name for item in response.output if item.type == "function_call"]
            text = response.output_text
            if text.strip():
                print(text)
            else:
                kinds = [item.type for item in response.output]
                print(f"(model returned no text; output items: {kinds})")
            print("─" * 78)
            print(f"tools called: {calls or '(none)'}")
    print(f"response id: {response_id}  |  {elapsed:.1f}s  |  reuse with --previous-response-id")
    return 0


if __name__ == "__main__":
    sys.exit(main())
