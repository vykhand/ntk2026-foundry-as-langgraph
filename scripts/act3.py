"""Act 3 — watch it: one traced call, then where to look.

    uv run act3                 # ask the Act 1 question, print response id + tools + the portal Traces link
    uv run act3 --kql           # also query Application Insights for the last 10 minutes (terminal fallback)
    uv run act3 "…vprašanje…"

The hosted agent emits server-side spans (Foundry Agent Service) and in-container spans (the
hosting library's OpenTelemetry distro) into the Application Insights resource connected to the
project. The portal's Traces tab is the stage view; ``--kql`` is the fallback when the portal is slow.
"""

from __future__ import annotations

import argparse
import base64
import os
import sys
import time
import uuid
from pathlib import Path
from typing import Any

from scripts.azdenv import load_env

ROOT = Path(__file__).resolve().parents[1]
ACT1_QUESTION = "Sestavi mi urnik za torek — zanima me AI in Azure, nič pred deveto, pusti mi luknjo za kavo."
PORTAL_ROOT = "https://ai.azure.com/nextgen/r"


def portal_org(subscription_id: str) -> str:
    """The portal URL's first segment: the subscription id's 16 bytes, base64url, unpadded."""
    try:
        raw = uuid.UUID(subscription_id).bytes
    except ValueError:  # unset, or not a subscription id: the link degrades, the command does not fail
        return ""
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def traces_url(*, org: str, resource_group: str, account: str, project: str, tenant: str) -> str:
    """The Foundry portal Traces tab for the agent (pattern from `azd ai agent show`'s playground URL)."""
    return f"{PORTAL_ROOT}/{org},{resource_group},,{account},{project}/build/agents/ntk-asistent/traces?tid={tenant}"


def portal_links(env: dict[str, str]) -> dict[str, str]:
    # Everything comes from the azd environment; nothing about this project's own subscription or
    # account is written into the code.
    rg = env.get("AZURE_RESOURCE_GROUP", "rg-ntk2026")
    account = env.get("AZURE_AI_ACCOUNT_NAME", "")
    project = env.get("AZURE_AI_PROJECT_NAME", "ntk2026")
    tenant = env.get("AZURE_TENANT_ID", "")
    org = portal_org(env.get("AZURE_SUBSCRIPTION_ID", ""))
    return {
        "traces": traces_url(org=org, resource_group=rg, account=account, project=project, tenant=tenant),
        "app_insights": (
            f"https://portal.azure.com/#@/resource/subscriptions/{env.get('AZURE_SUBSCRIPTION_ID', '')}"
            f"/resourceGroups/{rg}/providers/microsoft.insights/components/{env.get('NTK_APP_INSIGHTS', 'appi-ntk2026')}/overview"
        ),
    }


def span_table(rows: list[dict[str, Any]]) -> str:
    """Compact table of App Insights rows (name, kind, duration, gen_ai operation)."""
    if not rows:
        return "(no spans in the window yet — ingestion lags 1–3 minutes)"
    lines = [f"{'time':<8} {'kind':<11} {'ms':>7}  {'gen_ai op':<16} name"]
    for r in rows:
        ts = str(r.get("timestamp", ""))[11:19]
        dur = r.get("duration")
        ms = f"{float(dur):.0f}" if dur not in (None, "") else "-"
        lines.append(
            f"{ts:<8} {str(r.get('itemType', '')):<11} {ms:>7}  {str(r.get('op') or '-'):<16} {str(r.get('name', ''))[:60]}"
        )
    return "\n".join(lines)


LAW_KQL = (
    "union AppDependencies, AppRequests, AppTraces"
    " | where TimeGenerated > ago({minutes}m)"
    " | extend op = tostring(Properties['gen_ai.operation.name'])"
    " | project timestamp=TimeGenerated, itemType=Type, name=Name, duration=DurationMs, op, operation_Id=OperationId"
    " | order by timestamp desc | take {limit}"
)


def query_app_insights(*, workspace_id: str, minutes: int = 10, limit: int = 40) -> list[dict[str, Any]]:
    """Query the connected Log Analytics workspace with the azd credential (not the az CLI default).

    Uses azure-monitor-query so the token comes from ``DefaultAzureCredential`` — pinned to the azd
    login via ``AZURE_TOKEN_CREDENTIALS`` in ``.env`` — instead of whichever subscription the ``az``
    CLI happens to have selected (another session keeps flipping it, the talk's write-up).
    """
    from datetime import timedelta

    from azure.identity import DefaultAzureCredential
    from azure.monitor.query import LogsQueryClient

    client = LogsQueryClient(DefaultAzureCredential())
    response = client.query_workspace(
        workspace_id=workspace_id,
        query=LAW_KQL.format(minutes=minutes, limit=limit),
        timespan=timedelta(minutes=minutes),
    )
    tables = getattr(response, "tables", None) or getattr(response, "partial_data", None) or []
    if not tables:
        return []
    table = tables[0]
    cols = [c if isinstance(c, str) else c.name for c in table.columns]
    return [dict(zip(cols, row, strict=True)) for row in table.rows]


def main(argv: list[str] | None = None) -> int:
    load_env(ROOT)
    parser = argparse.ArgumentParser(description="Act 3: one traced call and the places to watch it")
    parser.add_argument("question", nargs="?", default=ACT1_QUESTION)
    parser.add_argument(
        "--kql", action="store_true", help="query Application Insights for the last 10 minutes"
    )
    parser.add_argument("--minutes", type=int, default=10)
    parser.add_argument("--no-call", action="store_true", help="only print the links (and --kql)")
    args = parser.parse_args(argv)

    env = dict(os.environ)
    links = portal_links(env)
    if not args.no_call:
        from scripts.invoke import _cloud_client

        client, base_url = _cloud_client(env.get("AGENT_NAME", "ntk-asistent"))
        print(f"→ {base_url}/responses")
        started = time.monotonic()
        response = client.responses.create(input=args.question)
        elapsed = time.monotonic() - started
        calls = [item.name for item in response.output if getattr(item, "type", "") == "function_call"]
        text = response.output_text.strip()
        print(text.split("```")[-1].strip() or text[:400])
        print("─" * 78)
        print(f"response id: {response.id}  |  {elapsed:.1f}s  |  tools: {', '.join(calls) or '(none)'}")
    print("─" * 78)
    print(f"Traces (portal):   {links['traces']}")
    print(f"App Insights:      {links['app_insights']}")
    if args.kql:
        workspace = env.get("NTK_LOG_ANALYTICS_WORKSPACE_ID", "")
        if not workspace:
            sys.exit(
                "NTK_LOG_ANALYTICS_WORKSPACE_ID is not set (azd env set NTK_LOG_ANALYTICS_WORKSPACE_ID <customerId>)"
            )
        print(span_table(query_app_insights(workspace_id=workspace, minutes=args.minutes)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
