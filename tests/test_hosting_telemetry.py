from __future__ import annotations

from hosting.telemetry import quiet_local_telemetry, telemetry_configured


def test_local_run_without_exporters_disables_the_sdk():
    env: dict[str, str] = {"LLM_PROVIDER": "ollama"}
    status = quiet_local_telemetry(env)
    assert env["OTEL_SDK_DISABLED"] == "true"
    assert status.startswith("telemetry: disabled")


def test_hosted_container_keeps_telemetry_on():
    env = {"APPLICATIONINSIGHTS_CONNECTION_STRING": "InstrumentationKey=abc"}
    quiet_local_telemetry(env)
    assert "OTEL_SDK_DISABLED" not in env
    assert telemetry_configured(env)


def test_foundry_project_endpoint_counts_as_configured():
    env = {"FOUNDRY_PROJECT_ENDPOINT": "https://x.services.ai.azure.com/api/projects/p"}
    quiet_local_telemetry(env)
    assert "OTEL_SDK_DISABLED" not in env


def test_explicit_setting_is_respected_either_way():
    env = {"OTEL_SDK_DISABLED": "false"}
    assert quiet_local_telemetry(env).endswith("(explicit)")
    assert env["OTEL_SDK_DISABLED"] == "false"
    env = {"OTEL_SDK_DISABLED": "true", "APPLICATIONINSIGHTS_CONNECTION_STRING": "x"}
    quiet_local_telemetry(env)
    assert env["OTEL_SDK_DISABLED"] == "true"


def test_blank_values_do_not_count_as_configured():
    assert not telemetry_configured({"OTEL_EXPORTER_OTLP_ENDPOINT": "   "})
