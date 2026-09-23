"""Act 1 — local first. One command: ``uv run act1``.

Starts the hosted-agent server (the same ``langchain_azure_ai.agents.hosting``
Responses host that runs in the cloud) on ``PORT`` (8088), waits until it
accepts connections, then opens the Agent Inspector (``azd ai inspector
launch``, UI on :8087) unless ``--no-inspector`` is given.

``--smoke`` instead sends the Act 1 question to the running server (starting
it if needed), prints the answer and exits non-zero if the agenda block is
missing — this is the acceptance check for "chat locally, offline, < 60 s".
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import signal
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
ACT1_QUESTION = "Sestavi mi urnik za torek — zanima me AI in Azure, nič pred deveto, pusti mi luknjo za kavo."
ACT1_DAY = "2026-09-22"  # "torek" in the question above
# The same request for the English notebook; the agent still answers in Slovene (its prompt says so).
ACT1_QUESTION_EN = (
    "Build me an agenda for Tuesday — I'm into AI and Azure, nothing before nine, leave me a coffee break."
)


def _port_open(port: int, host: str = "127.0.0.1") -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.5)
        return sock.connect_ex((host, port)) == 0


def _ready(port: int) -> bool:
    """The agent server exposes GET /readiness (azure-ai-agentserver-core)."""
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/readiness", timeout=1) as resp:
            return resp.status == 200
    except (urllib.error.URLError, OSError):
        return False


def _wait_for_port(port: int, timeout: float, proc: subprocess.Popen | None = None) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if proc is not None and proc.poll() is not None:
            return False
        if _port_open(port) and _ready(port):
            return True
        time.sleep(0.25)
    return False


def _check_ollama() -> str | None:
    """Return a warning when the configured local model is not reachable/pulled."""
    from hosting.llm import provider_name

    if provider_name() != "ollama":
        return None
    base = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434/v1").removesuffix("/v1")
    model = os.environ.get("OLLAMA_MODEL", "gpt-oss:20b")
    try:
        with urllib.request.urlopen(f"{base}/api/tags", timeout=3) as resp:
            names = {m.get("name") for m in json.load(resp).get("models", [])}
    except (urllib.error.URLError, OSError, ValueError):
        return f"Ollama not reachable at {base} — run `brew services start ollama`"
    if model not in names and f"{model}:latest" not in names:
        return f"model {model!r} not pulled — run `ollama pull {model}` (have: {sorted(names)})"
    return None


def start_server(port: int) -> subprocess.Popen:
    env = {**os.environ, "PORT": str(port)}
    cmd = [sys.executable, "-m", "hosting.serve"]
    return subprocess.Popen(cmd, cwd=ROOT, env=env)


def start_inspector(port: int, inspector_port: int) -> subprocess.Popen | None:
    azd = shutil.which("azd")
    if not azd:
        print(f"azd not found — open http://localhost:{port} manually or use the VS Code Agent Inspector")
        return None
    cmd = [azd, "ai", "inspector", "launch", "--port", str(port), "--inspector-port", str(inspector_port)]
    return subprocess.Popen(cmd, cwd=ROOT)


def ask(port: int, question: str, *, stream: bool = False, timeout: float = 240) -> dict:
    body = json.dumps({"input": question, "stream": stream}).encode("utf-8")
    req = urllib.request.Request(
        f"http://127.0.0.1:{port}/responses",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.load(resp)


def output_text(response: dict) -> str:
    """Concatenate the assistant text from a Responses API object."""
    parts: list[str] = []
    for item in response.get("output", []):
        if item.get("type") != "message":
            continue
        for content in item.get("content", []):
            if content.get("type") in ("output_text", "text"):
                parts.append(content.get("text", ""))
    return "\n".join(parts)


def tool_calls(response: dict) -> list[str]:
    items = response.get("output", [])
    return [item.get("name", "?") for item in items if item.get("type") == "function_call"]


def smoke(port: int, question: str, day: str | None) -> int:
    from agent.contract import extract_agenda, resolve_items
    from agent.metrics import evaluate_agenda
    from agent.preferences import get_persona
    from agent.program import load_program

    started = time.monotonic()
    response = ask(port, question)
    elapsed = time.monotonic() - started
    text = output_text(response)
    print("─" * 78)
    print(text)
    print("─" * 78)
    calls = tool_calls(response)
    print(f"tools called: {calls or '(none)'}  |  {elapsed:.1f}s  |  response id {response.get('id')}")
    agenda = extract_agenda(text)
    if agenda is None:
        print("SMOKE FAIL: no agenda JSON block in the answer")
        return 2
    program = load_program()
    resolved = resolve_items(agenda, program.get)
    persona = get_persona()
    report = evaluate_agenda(resolved["items"], persona, day=day)
    violations = report["preference_violations"]
    coffee = "ok" if report["break_coverage"]["ok"] else "MISSING"
    print(
        f"agenda: {report['items']} talks | clashes {report['clash_count']} | "
        f"pref violations {violations['count']} (off-day {len(violations['off_day'])}, "
        f"before {violations['earliest_start'] or '-'}: {len(violations['before_earliest'])}) | "
        f"coffee gap {coffee} | unknown ids {resolved['unknown_ids'] or 'none'}"
    )
    print(f"eval verdict: {'OK' if report['ok'] else 'HEADROOM (expected with the baseline prompt)'}")
    return 0


def main(argv: list[str] | None = None) -> int:
    load_dotenv(ROOT / ".env")
    parser = argparse.ArgumentParser(description="Act 1 — run the NTK asistent locally")
    parser.add_argument("--port", type=int, default=int(os.environ.get("PORT", "8088")))
    parser.add_argument("--inspector-port", type=int, default=8087)
    parser.add_argument("--no-inspector", action="store_true", help="do not open the Agent Inspector")
    parser.add_argument("--smoke", action="store_true", help="send the Act 1 question and exit")
    parser.add_argument("--question", default=ACT1_QUESTION)
    parser.add_argument("--day", default=ACT1_DAY, help="requested day (ISO) the smoke scores against")
    parser.add_argument("--startup-timeout", type=float, default=60)
    args = parser.parse_args(argv)

    from hosting.llm import describe

    prompt_file = os.environ.get("NTK_PROMPT_FILE", "prompts/baseline_v1.md")
    print(f"NTK asistent · model {describe()} · prompt {prompt_file}")
    warning = _check_ollama()
    if warning:
        print(f"WARNING: {warning}")

    server: subprocess.Popen | None = None
    if _port_open(args.port):
        print(f"server already listening on :{args.port} — reusing it")
    else:
        server = start_server(args.port)
        print(f"starting host on :{args.port} …", end=" ", flush=True)
        if not _wait_for_port(args.port, args.startup_timeout, server):
            print("FAILED (server exited or timed out)")
            return 1
        print("ready")

    try:
        if args.smoke:
            return smoke(args.port, args.question, args.day or None)
        inspector = None if args.no_inspector else start_inspector(args.port, args.inspector_port)
        print()
        print("Act 1 question →", args.question)
        print("Ctrl+C stops everything.")
        try:
            if server is not None:
                server.wait()
            elif inspector is not None:
                inspector.wait()
            else:
                signal.pause()
        except KeyboardInterrupt:
            pass
        finally:
            if inspector is not None and inspector.poll() is None:
                inspector.terminate()
        return 0
    finally:
        if server is not None and server.poll() is None:
            server.terminate()
            try:
                server.wait(timeout=10)
            except subprocess.TimeoutExpired:
                server.kill()


if __name__ == "__main__":
    sys.exit(main())
