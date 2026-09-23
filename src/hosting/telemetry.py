"""Keep local runs quiet; leave cloud telemetry untouched.

The agent server configures OpenTelemetry through the ``microsoft-opentelemetry``
distro, which *auto-enables console exporters when no other destination is
active*: every span is printed as it ends and a metrics dump lands on stdout
every minute. Fine for debugging, unusable on stage.

Rule: when nothing says "export somewhere" — no App Insights connection string
(injected in hosted containers), no OTLP endpoint, no Foundry project — set
``OTEL_SDK_DISABLED=true`` before the server builds its providers. The
OpenTelemetry SDK honours that variable for traces, metrics and logs. Verified
2026-09-05 (the talk's write-up, D-17). Set any of the export variables, or
``OTEL_SDK_DISABLED=false``, to opt back in locally (Act 3 rehearsal).
"""

from __future__ import annotations

import os

EXPORT_SIGNALS = (
    "APPLICATIONINSIGHTS_CONNECTION_STRING",
    "APPLICATION_INSIGHTS_CONNECTION_STRING",  # spelling used by some samples
    "OTEL_EXPORTER_OTLP_ENDPOINT",
    "OTEL_EXPORTER_OTLP_TRACES_ENDPOINT",
    "FOUNDRY_PROJECT_ENDPOINT",
    "FOUNDRY_HOSTING_ENVIRONMENT",
)


def telemetry_configured(env: dict[str, str] | os._Environ[str] | None = None) -> bool:
    env = os.environ if env is None else env
    return any(env.get(name, "").strip() for name in EXPORT_SIGNALS)


def quiet_local_telemetry(env: dict[str, str] | os._Environ[str] | None = None) -> str:
    """Disable the OTel SDK for purely local runs. Returns a one-line status for logs."""
    env = os.environ if env is None else env
    explicit = env.get("OTEL_SDK_DISABLED", "").strip().lower()
    if explicit:
        return f"telemetry: OTEL_SDK_DISABLED={explicit} (explicit)"
    if telemetry_configured(env):
        return "telemetry: exporting (connection string / OTLP endpoint / Foundry project present)"
    env["OTEL_SDK_DISABLED"] = "true"
    return "telemetry: disabled for this local run (set APPLICATIONINSIGHTS_CONNECTION_STRING to export)"


__all__ = ["EXPORT_SIGNALS", "quiet_local_telemetry", "telemetry_configured"]
