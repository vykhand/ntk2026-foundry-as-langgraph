"""Telegram front end for the deployed agent — the stage beat where the room joins in.

    uv run bot                     # long-poll Telegram, forward to the agent in Azure
    uv run bot --dry-run "…"       # no Telegram: one question straight to the agent
    uv run bot --local --port 8088 # against the local host instead of the cloud

The bot is a *client*, not a second deployment. It holds no logic: it takes a Telegram message,
hands the text to the hosted agent over the Responses protocol, and puts the answer back. That is
the point on stage — the thing doing the work is the agent in Azure, and every message the room
sends becomes a trace there, in its own isolated session.

Long polling rather than a webhook, deliberately: a webhook needs a public HTTPS endpoint, and a
conference hall is the worst possible place to discover that yours is unreachable.

Setup (once, and the token is the speaker's to create — talk to @BotFather in Telegram):

    /newbot  →  copy the token  →  put it in .env as TELEGRAM_BOT_TOKEN=…

``.env`` is git-ignored. The token never needs to appear anywhere else.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

import httpx

from scripts.azdenv import load_env

ROOT = Path(__file__).resolve().parents[1]
API = "https://api.telegram.org"
POLL_TIMEOUT = 25  # seconds Telegram holds the long poll open
MAX_MESSAGE = 4096  # Telegram's hard limit on a message body

WELCOME = (
    "Živjo! Sem NTK asistent 🤖\n\n"
    "Sestavim ti osebni urnik NT konference 2026. Napiši mi, kaj te zanima in kdaj moraš oditi.\n\n"
    "Na primer:\n"
    "• „Zanima me AI in Azure, v torek, nič pred deveto.\"\n"
    "• „Sem Nina — v sredo bi šla na podatke in Fabric.\"\n"
    "• „Ponedeljek popoldne, varnost. Ob štirih grem domov.\"\n\n"
    "Odgovarjam v slovenščini. Vsak pogovor teče v svoji seji v Azure."
)

THINKING = "Sestavljam urnik… 🗓"

# What a failed call puts in the chat. Never the exception: an Azure auth error names the signed-in
# account, and on stage this chat is on a hundred phones and the projector. Details go to stderr.
SORRY = "Ups — agent ta trenutek ne odgovarja. Poskusi znova čez minuto."


class AgentSilent(RuntimeError):
    """The agent returned no text; the reason is for the speaker's terminal, not for the chat."""


class Agent:
    """The deployed agent, one conversation per Telegram chat."""

    def __init__(self, *, local: bool, port: int, agent_name: str) -> None:
        from scripts.invoke import _cloud_client, _local_client

        self.client, self.base_url = (
            _local_client(port) if local else _cloud_client(agent_name)
        )
        # Responses threading: the previous id is how the hosted agent gets the conversation back
        # without us keeping any state of our own. One id per chat = one conversation per person.
        self.previous: dict[int, str] = {}

    def ask(self, chat_id: int, question: str) -> tuple[str, str | None, float]:
        started = time.monotonic()
        kwargs: dict[str, Any] = {"input": question}
        if chat_id in self.previous:
            kwargs["previous_response_id"] = self.previous[chat_id]
        response = self.client.responses.create(**kwargs)
        self.previous[chat_id] = response.id
        text = response.output_text or ""
        if not text.strip():
            # Over the deployment's rate limit the hosted agent answers HTTP 200 with an empty
            # body and the reason only in `error` (the talk's write-up, D-22) — say so rather than go quiet.
            error = getattr(response, "error", None)
            reason = getattr(error, "message", None) or (str(error) if error else "prazen odgovor")
            raise AgentSilent(reason)
        return text, response.id, time.monotonic() - started

    def forget(self, chat_id: int) -> None:
        self.previous.pop(chat_id, None)


def _format(answer: str) -> str:
    """Telegram is a chat window, not a terminal: the agenda as a list, then the sentence.

    **The last agenda wins, not all of them.** The deployed graph re-checks its own answer before
    sending it, and the hosting layer streams every node's message, so a corrected turn arrives
    carrying the rejected draft *and* the repair (the talk's write-up, S-08e). Concatenating every fenced
    block would put thirteen talks on someone's phone, half of them the ones the agent just threw
    away — the same trap ``agent.contract.extract_agenda`` exists to avoid, one layer up.
    """
    parts = answer.split("```")
    fenced = [p for i, p in enumerate(parts) if i % 2 == 1]
    agenda = None
    for block in fenced:
        body = block[4:] if block.lower().startswith("json") else block
        try:
            candidate = json.loads(body)
        except (json.JSONDecodeError, ValueError):
            continue
        if isinstance(candidate, dict) and isinstance(candidate.get("items"), list):
            agenda = candidate  # keep going: the last one is the one the agent stands behind

    # The prose after the final block is the narration for the agenda we kept; earlier prose
    # belongs to the draft and would explain a schedule the reader never sees.
    prose = parts[-1].strip() if len(parts) > 1 else answer.strip()

    talks = []
    for item in (agenda or {}).get("items", []):
        start = str(item.get("start", ""))[11:16]
        end = str(item.get("end", ""))[11:16]
        talks.append(f"🕘 {start}–{end}  {item.get('title', '')}  ({item.get('room', '')})")
    lines = talks + ([""] + [prose] if prose else [])
    return "\n".join(lines).strip()[:MAX_MESSAGE] or prose[:MAX_MESSAGE] or "…"


class Telegram:
    def __init__(self, token: str) -> None:
        self.url = f"{API}/bot{token}"
        self.http = httpx.Client(timeout=POLL_TIMEOUT + 10)

    def call(self, method: str, **payload: Any) -> Any:
        response = self.http.post(f"{self.url}/{method}", json=payload)
        response.raise_for_status()
        body = response.json()
        if not body.get("ok"):
            raise RuntimeError(f"{method}: {body}")
        return body["result"]

    def me(self) -> dict[str, Any]:
        return self.call("getMe")

    def updates(self, offset: int | None) -> list[dict[str, Any]]:
        payload: dict[str, Any] = {"timeout": POLL_TIMEOUT, "allowed_updates": ["message"]}
        if offset is not None:
            payload["offset"] = offset
        return self.call("getUpdates", **payload)

    def send(self, chat_id: int, text: str) -> dict[str, Any]:
        return self.call("sendMessage", chat_id=chat_id, text=text[:MAX_MESSAGE])

    def edit(self, chat_id: int, message_id: int, text: str) -> None:
        try:
            self.call("editMessageText", chat_id=chat_id, message_id=message_id, text=text[:MAX_MESSAGE])
        except Exception:  # a failed edit must never lose the answer
            self.send(chat_id, text)


def serve(bot: Telegram, agent: Agent) -> int:
    who = bot.me()
    print(
        f"→ @{who.get('username')} ({who.get('first_name')})  ·  agent {agent.base_url}",
        file=sys.stderr,
        flush=True,
    )
    offset: int | None = None
    while True:
        try:
            updates = bot.updates(offset)
        except (httpx.HTTPError, RuntimeError) as exc:
            print(f"  telegram: {exc} — retrying in 3 s", file=sys.stderr, flush=True)
            time.sleep(3)
            continue

        for update in updates:
            offset = update["update_id"] + 1
            message = update.get("message") or {}
            chat_id = (message.get("chat") or {}).get("id")
            text = (message.get("text") or "").strip()
            if not chat_id or not text:
                continue
            name = (message.get("from") or {}).get("first_name", "?")

            if text.startswith("/start") or text.startswith("/help"):
                bot.send(chat_id, WELCOME)
                continue
            if text.startswith("/nov") or text.startswith("/reset"):
                agent.forget(chat_id)
                bot.send(chat_id, "Začnimo znova. Kaj te zanima?")
                continue

            placeholder = bot.send(chat_id, THINKING)
            try:
                answer, response_id, seconds = agent.ask(chat_id, text)
            except Exception as exc:  # one bad call must not take the bot down mid-talk
                bot.edit(chat_id, placeholder["message_id"], SORRY)
                print(f"  {name}: {type(exc).__name__}: {exc}", file=sys.stderr, flush=True)
                continue
            bot.edit(chat_id, placeholder["message_id"], _format(answer))
            print(
                f"  {name} ({chat_id}) · {seconds:.1f}s · {response_id}",
                file=sys.stderr,
                flush=True,
            )


def main(argv: list[str] | None = None) -> int:
    load_env(ROOT)
    parser = argparse.ArgumentParser(description="Telegram front end for the deployed NTK asistent")
    parser.add_argument("--local", action="store_true", help="target the local host, not Foundry")
    parser.add_argument("--port", type=int, default=int(os.environ.get("PORT", "8088")))
    parser.add_argument("--agent", default=os.environ.get("AGENT_NAME", "ntk-asistent"))
    parser.add_argument(
        "--dry-run",
        nargs="?",
        const="Zanima me AI in Azure, v torek, nič pred deveto.",
        default=None,
        help="skip Telegram entirely: ask the agent one question and print what the bot would send",
    )
    args = parser.parse_args(argv)

    agent = Agent(local=args.local, port=args.port, agent_name=args.agent)

    if args.dry_run is not None:
        print(f"→ {agent.base_url}\n")
        try:
            answer, response_id, seconds = agent.ask(0, args.dry_run)
        except AgentSilent as exc:
            print(f"Agent ni odgovoril: {exc}\n\nV klepet bi šlo: {SORRY}")
            return 1
        print(_format(answer))
        print(f"\n— {seconds:.1f}s · {response_id}")
        return 0

    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    if not token:
        sys.exit(
            "TELEGRAM_BOT_TOKEN is not set.\n"
            "  1. In Telegram, message @BotFather and send /newbot\n"
            "  2. Put the token it gives you in .env as TELEGRAM_BOT_TOKEN=…  (.env is git-ignored)\n"
            "  3. uv run bot\n"
            "No token to hand? `uv run bot --dry-run` exercises the agent path without Telegram."
        )
    if not args.local:
        _preflight_azure()
    return serve(Telegram(token), agent)


def _preflight_azure() -> None:
    """Fail at startup, not on the first message from the audience.

    The bot borrows whatever account `azd` is signed in with. On a box where another session flips
    that login, a bot started in the morning answers every message of the afternoon with an
    apology — so get one token now and refuse to start if it cannot be had.
    """
    from azure.identity import DefaultAzureCredential

    from scripts.invoke import _AZURE_AI_SCOPE

    try:
        DefaultAzureCredential().get_token(_AZURE_AI_SCOPE)
    except Exception as exc:
        detail = next((line.strip() for line in str(exc).splitlines() if "ERROR" in line), "")
        sys.exit(
            "Azure sign-in does not reach the agent, so every answer would fail.\n"
            "  Sign in to this project's own az profile: uv run az-login  (then --check)\n"
            f"  {detail[:300]}"
        )


if __name__ == "__main__":
    raise SystemExit(main())
