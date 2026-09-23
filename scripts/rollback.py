"""Roll the hosted agent's traffic back to an earlier version — the Act 2 "oops" beat.

azd has no rollback command (the talk's write-up, D-12). Every ``azd deploy`` creates a new immutable
version and moves the endpoint's *version selector* to it; rolling back is the same selector
update pointed at an older version, one SDK call::

    uv run rollback --list        # versions + the one currently taking traffic
    uv run rollback 1             # 100 % of traffic to version 1 (the endpoint URL is unchanged)
    uv run rollback 1 --dry-run   # print the merge-patch body without sending it

Reads ``FOUNDRY_PROJECT_ENDPOINT`` from the environment, ``.env``, or the selected azd
environment (``.azure/<env>/.env``), and needs an Entra login with the Foundry User role on the
project (the same one ``uv run invoke`` uses).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

from scripts.azdenv import load_env

ROOT = Path(__file__).resolve().parents[1]


LATEST = "@latest"  # the selector Foundry sets on a fresh agent: every deploy takes the traffic


def normalize_version(version: str | int) -> str:
    """``1`` → ``"1"``; ``latest`` / ``@latest`` → ``"@latest"`` (the platform's own alias)."""
    text = str(version).strip()
    if not text:
        raise ValueError("version must not be empty")
    if text.lstrip("@").lower() == "latest":
        return LATEST
    return text


def selector_patch(version: str | int, *, traffic_percentage: int = 100) -> dict[str, Any]:
    """The merge-patch body for ``agents.update_details`` that pins all traffic to one version.

    Pure function so the shape can be unit-tested (and shown on a slide) without a project.
    """
    version = normalize_version(version)
    if not 0 <= int(traffic_percentage) <= 100:
        raise ValueError("traffic_percentage must be between 0 and 100")
    return {
        "agent_endpoint": {
            "version_selector": {
                "version_selection_rules": [
                    {
                        "type": "FixedRatio",
                        "agent_version": version,
                        "traffic_percentage": int(traffic_percentage),
                    }
                ]
            }
        }
    }


def active_versions(details: Any) -> list[tuple[str, int]]:
    """``[(version, traffic_percentage), ...]`` from an ``AgentDetails``-like mapping."""
    endpoint = _get(details, "agent_endpoint") or {}
    selector = _get(endpoint, "version_selector") or {}
    rules = _get(selector, "version_selection_rules") or []
    out: list[tuple[str, int]] = []
    for rule in rules:
        version = _get(rule, "agent_version")
        if version is None:
            continue
        out.append((str(version), int(_get(rule, "traffic_percentage") or 0)))
    return out


def selector_summary(live: list[tuple[str, int]], latest_version: str | None) -> str:
    """One line describing where the traffic goes, resolving ``@latest`` to the real version."""
    if not live:
        return "traffic: no version selector set (the platform serves the latest version)"
    parts = []
    for version, share in live:
        target = f"{LATEST} (= v{latest_version})" if version == LATEST and latest_version else f"v{version}"
        parts.append(f"{share} % → {target}")
    return "traffic: " + ", ".join(parts)


def _fmt_time(value: Any) -> str:
    if isinstance(value, int | float):
        from datetime import UTC, datetime

        return datetime.fromtimestamp(value, tz=UTC).strftime("%Y-%m-%d %H:%M:%SZ")
    return str(value or "")


def _get(obj: Any, key: str) -> Any:
    if obj is None:
        return None
    if isinstance(obj, dict):
        return obj.get(key)
    try:
        return obj[key]
    except (KeyError, TypeError, IndexError):
        return getattr(obj, key, None)


def _client():
    from azure.ai.projects import AIProjectClient
    from azure.identity import DefaultAzureCredential

    endpoint = os.environ.get("FOUNDRY_PROJECT_ENDPOINT", "").rstrip("/")
    if not endpoint:
        sys.exit("FOUNDRY_PROJECT_ENDPOINT is not set (azd env get-values, or .env)")
    return AIProjectClient(endpoint=endpoint, credential=DefaultAzureCredential())


def version_payload(agent_name: str | None = None) -> dict[str, Any]:
    """The same data `--list` prints, as data rather than a printed report.

    Read-only: `agents.get` + `list_versions`, never `update_details`. `notebooks/02_deploy.py`
    shows exactly this, so the version table on stage and the one in the terminal cannot disagree.
    Acquiring a credential is slow from cold, which is why the notebook keeps it behind
    `ntk.cached()` and `scripts/warm_cache.py` exists to fill that cache off the stage clock.
    """
    load_env(ROOT)
    name = agent_name or os.environ.get("AGENT_NAME", "ntk-asistent")
    client = _client()
    details = client.agents.get(name)
    live = active_versions(details)
    latest = _get(_get(details, "versions"), "latest")
    latest_version = str(_get(latest, "version")) if latest is not None else None
    shares = {(latest_version if v == LATEST else v): share for v, share in live}
    rows = []
    for item in client.agents.list_versions(name, order="asc"):
        version = str(_get(item, "version"))
        rows.append(
            {
                "version": version,
                "status": str(_get(item, "status") or ""),
                "created_at": _fmt_time(_get(item, "created_at")),
                "traffic_percentage": shares.get(version),
            }
        )
    return {"agent_name": name, "latest_version": latest_version, "versions": rows}


def _print_versions(client: Any, agent_name: str) -> None:
    details = client.agents.get(agent_name)
    live = active_versions(details)
    latest = _get(_get(details, "versions"), "latest")
    latest_version = str(_get(latest, "version")) if latest is not None else None
    print(f"agent {agent_name} · state {_get(details, 'state')} · latest version {latest_version or '?'}")
    shares = {(latest_version if v == LATEST else v): share for v, share in live}
    for item in client.agents.list_versions(agent_name, order="asc"):
        version = str(_get(item, "version"))
        share = shares.get(version)
        marker = f"  ← {share} % of traffic" if share is not None else ""
        created = _fmt_time(_get(item, "created_at"))
        status = _get(item, "status")
        print(f"  v{version:<4} {status or '':<10} {created}{marker}")
    print("  " + selector_summary(live, latest_version))


def main(argv: list[str] | None = None) -> int:
    load_env(ROOT)
    parser = argparse.ArgumentParser(description="Route the hosted agent's traffic to a given version")
    parser.add_argument(
        "version", nargs="?", help="agent version to route 100 %% of traffic to (or `latest` to undo a pin)"
    )
    parser.add_argument("--agent", default=os.environ.get("AGENT_NAME", "ntk-asistent"))
    parser.add_argument("--list", action="store_true", help="show versions and the live selector")
    parser.add_argument("--dry-run", action="store_true", help="print the patch, do not send it")
    args = parser.parse_args(argv)

    if not args.list and args.version is None:
        parser.error("give a version to roll back to, or --list")

    patch = selector_patch(args.version) if args.version is not None else None
    if args.dry_run:
        print(json.dumps({"agent_name": args.agent, "body": patch}, indent=2))
        return 0

    client = _client()
    if args.list or patch is None:
        _print_versions(client, args.agent)
        if patch is None:
            return 0

    from azure.ai.projects.models import (
        AgentEndpointConfig,
        FixedRatioVersionSelectionRule,
        VersionSelector,
    )

    assert args.version is not None  # parser.error above guarantees it
    target = normalize_version(args.version)
    # The slide version of this call: one merge-patch on the endpoint, the URL never changes.
    result = client.agents.update_details(
        args.agent,
        agent_endpoint=AgentEndpointConfig(
            version_selector=VersionSelector(
                version_selection_rules=[
                    FixedRatioVersionSelectionRule(agent_version=target, traffic_percentage=100)
                ]
            )
        ),
    )
    latest = _get(_get(result, "versions"), "latest")
    print(selector_summary(active_versions(result), str(_get(latest, "version")) if latest else None))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
