"""Give this project an Azure login nothing else on the laptop can switch.

    uv run az-login              # once: browser sign-in into the project's own az profile
    uv run az-login --check      # before any cloud work, and before walking on stage
    eval "$(uv run az-login --print-env)"   # a terminal where you will type azd by hand

**Why this exists (the talk's write-up, S-09).** `azd` here delegates to `az` (`auth.useAzCliAuth`), and `az`
answers with whatever subscription is the *default* in ``~/.azure``. Another session on this Mac
works in a different tenant and sets that default back to its own account, so the Telegram bot,
`uv run invoke` and `azd deploy` all silently changed identity between one hour and the next —
the bot answered every message with an authentication error.

``AZURE_CONFIG_DIR`` moves the whole az profile (accounts, token cache, default subscription) into
a directory only this project uses. Every Python script already loads ``.env`` before touching
Azure, and `azd`/`az` are child processes, so one line in ``.env`` covers them all. Extensions are
shared with the normal profile (``AZURE_EXTENSION_DIR``) — only the login is separate.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

from scripts.azdenv import load_env

ROOT = Path(__file__).resolve().parents[1]
DOTENV = ROOT / ".env"
CONFIG_DIR = Path.home() / ".azure-ntk2026"
SHARED_EXTENSIONS = Path.home() / ".azure" / "cliextensions"
SCOPE = "https://ai.azure.com/.default"


def _ensure_dotenv() -> Path:
    """Put AZURE_CONFIG_DIR in .env once; an explicit value already there wins."""
    text = DOTENV.read_text(encoding="utf-8") if DOTENV.exists() else ""
    for line in text.splitlines():
        if line.startswith("AZURE_CONFIG_DIR="):
            return Path(line.split("=", 1)[1].strip()).expanduser()
    block = (
        "\n# This project's own az login (uv run az-login) — immune to the default subscription\n"
        "# another session sets in ~/.azure. azd delegates to az, so this covers azd too.\n"
        f"AZURE_CONFIG_DIR={CONFIG_DIR}\n"
    )
    DOTENV.write_text(text.rstrip("\n") + "\n" + block if text else block.lstrip("\n"), encoding="utf-8")
    print(f"az-login: added AZURE_CONFIG_DIR={CONFIG_DIR} to .env")
    return CONFIG_DIR


def _apply(config_dir: Path) -> None:
    os.environ["AZURE_CONFIG_DIR"] = str(config_dir)
    if SHARED_EXTENSIONS.is_dir():
        os.environ.setdefault("AZURE_EXTENSION_DIR", str(SHARED_EXTENSIONS))


def _az(*args: str, capture: bool = True, profile: bool = True) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    if not profile:  # read the *normal* profile, e.g. to learn a tenant id before the first login
        env.pop("AZURE_CONFIG_DIR", None)
    return subprocess.run(["az", *args], capture_output=capture, text=True, env=env, check=False)


def _target() -> tuple[str, str | None]:
    subscription = os.environ.get("AZURE_SUBSCRIPTION_ID", "").strip()
    if not subscription:
        sys.exit("az-login: AZURE_SUBSCRIPTION_ID is not set — select the azd env (azd env select ntk2026)")
    tenant = os.environ.get("AZURE_TENANT_ID", "").strip() or None
    if tenant is None:
        query = ("account", "show", "--subscription", subscription, "--query", "tenantId", "-o", "tsv")
        tenant = _az(*query, profile=False).stdout.strip() or None
    return subscription, tenant


def check(subscription: str) -> int:
    shown = _az("account", "show", "-o", "json")
    if shown.returncode != 0:
        print("az-login: the project profile has no login yet — run `uv run az-login`")
        return 1
    account = json.loads(shown.stdout)
    who = f"{account['user']['name']} · {account['name']}"
    if account["id"] != subscription:
        print(f"az-login: wrong default in the project profile ({who}); want {subscription}")
        print(f"  fix: uv run az-login, or az account set --subscription {subscription} in that profile")
        return 1

    # The chain the bot and the scripts really use: DefaultAzureCredential → azd → az (this profile).
    from azure.identity import DefaultAzureCredential

    try:
        DefaultAzureCredential().get_token(SCOPE)
    except Exception as exc:
        detail = next((ln.strip() for ln in str(exc).splitlines() if "ERROR" in ln), str(exc)[:200])
        print(f"az-login: az is right ({who}) but the token chain is not:\n  {detail[:300]}")
        print("  if azd was switched back to its own login: azd config set auth.useAzCliAuth true")
        return 1
    print(f"az-login: ok · {who} · profile {os.environ['AZURE_CONFIG_DIR']}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="This project's own az login")
    parser.add_argument("--check", action="store_true", help="verify the login reaches the agent")
    parser.add_argument("--print-env", action="store_true", help="print export lines for a shell")
    args = parser.parse_args(argv)

    if shutil.which("az") is None:
        sys.exit("az-login: the Azure CLI (az) is not installed")
    config_dir = _ensure_dotenv()
    load_env(ROOT)
    _apply(config_dir)

    if args.print_env:
        print(f"export AZURE_CONFIG_DIR={os.environ['AZURE_CONFIG_DIR']}")
        if "AZURE_EXTENSION_DIR" in os.environ:
            print(f"export AZURE_EXTENSION_DIR={os.environ['AZURE_EXTENSION_DIR']}")
        return 0

    subscription, tenant = _target()
    if args.check:
        return check(subscription)

    config_dir.mkdir(mode=0o700, exist_ok=True)
    login = ["login"] + (["--tenant", tenant] if tenant else [])
    print(f"az-login: signing in to {config_dir} — use the account that owns subscription {subscription}")
    if _az(*login, "-o", "none", capture=False).returncode != 0:
        return 1
    if _az("account", "set", "--subscription", subscription, capture=False).returncode != 0:
        return 1
    return check(subscription)


if __name__ == "__main__":
    raise SystemExit(main())
