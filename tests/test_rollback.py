"""The rollback script's pure parts: the merge-patch body and the live-selector reader."""

import json

import pytest
from scripts import rollback


def test_selector_patch_pins_all_traffic_to_one_version():
    patch = rollback.selector_patch("1")
    rules = patch["agent_endpoint"]["version_selector"]["version_selection_rules"]
    assert rules == [{"type": "FixedRatio", "agent_version": "1", "traffic_percentage": 100}]
    json.dumps(patch)  # must be plain JSON — it is a merge-patch body


def test_selector_patch_accepts_ints_and_strips():
    assert (
        rollback.selector_patch(3)["agent_endpoint"]["version_selector"]["version_selection_rules"][0][
            "agent_version"
        ]
        == "3"
    )
    assert (
        rollback.selector_patch(" 2 ")["agent_endpoint"]["version_selector"]["version_selection_rules"][0][
            "agent_version"
        ]
        == "2"
    )


@pytest.mark.parametrize("alias", ["latest", "@latest", "LATEST", " latest "])
def test_selector_patch_latest_alias_is_the_platform_default(alias):
    """`uv run rollback latest` undoes a pin: Foundry's own selector on a fresh agent is `@latest`."""
    rule = rollback.selector_patch(alias)["agent_endpoint"]["version_selector"]["version_selection_rules"][0]
    assert rule["agent_version"] == "@latest"


def test_selector_summary_resolves_latest_and_handles_empty():
    assert rollback.selector_summary([], "3") == (
        "traffic: no version selector set (the platform serves the latest version)"
    )
    assert rollback.selector_summary([("@latest", 100)], "2") == "traffic: 100 % → @latest (= v2)"
    assert rollback.selector_summary([("1", 100)], "2") == "traffic: 100 % → v1"
    assert rollback.selector_summary([("2", 90), ("1", 10)], "2") == "traffic: 90 % → v2, 10 % → v1"


@pytest.mark.parametrize("bad", ["", "   "])
def test_selector_patch_rejects_empty_version(bad):
    with pytest.raises(ValueError):
        rollback.selector_patch(bad)


@pytest.mark.parametrize("pct", [-1, 101])
def test_selector_patch_rejects_bad_percentage(pct):
    with pytest.raises(ValueError):
        rollback.selector_patch("1", traffic_percentage=pct)


def test_selector_patch_matches_sdk_model_wire_shape():
    """The dict body and the typed SDK models must serialise to the same JSON."""
    from azure.ai.projects.models import (
        AgentEndpointConfig,
        FixedRatioVersionSelectionRule,
        VersionSelector,
    )

    typed = AgentEndpointConfig(
        version_selector=VersionSelector(
            version_selection_rules=[
                FixedRatioVersionSelectionRule(agent_version="1", traffic_percentage=100)
            ]
        )
    )
    assert typed.as_dict() == rollback.selector_patch("1")["agent_endpoint"]


def test_active_versions_reads_dicts_and_models():
    details = {
        "agent_endpoint": {
            "version_selector": {
                "version_selection_rules": [
                    {"type": "FixedRatio", "agent_version": "2", "traffic_percentage": 90},
                    {"type": "FixedRatio", "agent_version": "1", "traffic_percentage": 10},
                ]
            }
        }
    }
    assert rollback.active_versions(details) == [("2", 90), ("1", 10)]

    from azure.ai.projects.models import (
        AgentEndpointConfig,
        FixedRatioVersionSelectionRule,
        VersionSelector,
    )

    typed = AgentEndpointConfig(
        version_selector=VersionSelector(
            version_selection_rules=[
                FixedRatioVersionSelectionRule(agent_version="3", traffic_percentage=100)
            ]
        )
    )
    assert rollback.active_versions({"agent_endpoint": typed}) == [("3", 100)]


def test_active_versions_tolerates_missing_selector():
    assert rollback.active_versions({}) == []
    assert rollback.active_versions({"agent_endpoint": {}}) == []
    assert rollback.active_versions(None) == []


def test_dry_run_prints_the_patch_without_a_project(capsys, monkeypatch):
    monkeypatch.delenv("FOUNDRY_PROJECT_ENDPOINT", raising=False)
    assert rollback.main(["1", "--dry-run", "--agent", "ntk-asistent"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["agent_name"] == "ntk-asistent"
    assert out["body"] == rollback.selector_patch("1")


def test_main_requires_a_version_or_list():
    with pytest.raises(SystemExit):
        rollback.main([])
