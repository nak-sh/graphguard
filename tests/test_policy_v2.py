"""Pure deterministic policy tests (no FalkorDB required)."""

from apps.graph_tools.models import CycleResult, MoneyPathResult, SharedInfraResult
from apps.policy.scorer import explain_non_escalation, load_policy, score_evidence, score_investigation


def _ring():
    return CycleResult(
        entity_id="A-104",
        cycle_nodes=["A-104", "A-105", "A-106", "A-107", "A-108", "A-104"],
        amounts=[9500.0, 9400.0, 9350.0, 9200.0, 9000.0],
        timestamps=[100, 200, 300, 400, 500],
        is_time_ordered=True,
        time_window_seconds=1000,
    )


def test_policy_weights_and_threshold_are_loaded_from_versioned_yaml():
    policy = load_policy()
    assert policy.version == "2026-10-v1"
    assert policy.signals["TIME_ORDERED_CYCLE"]["weight"] == 40
    assert policy.thresholds["high"] == 70


def test_ring_reaches_hold_threshold_from_supplied_evidence():
    infra = SharedInfraResult(
        entity_id="A-104",
        infrastructure_id="DEV-999",
        infrastructure_type="Device",
        connected_accounts=["A-105", "A-106", "A-107", "A-108"],
    )
    result = score_investigation("A-104", [infra], [_ring()])
    assert result.score >= 70
    assert result.tier == "AUTO_HOLD"
    assert {signal["rule"] for signal in result.signals} >= {
        "TIME_ORDERED_CYCLE",
        "RAPID_PASS_THROUGH",
        "SHARED_DEVICE_CLUSTER",
    }


def test_decoy_and_hub_do_not_escalate():
    household = SharedInfraResult(
        entity_id="D-201",
        infrastructure_id="DEV-FAMILY-1",
        infrastructure_type="Device",
        connected_accounts=["D-202"],
    )
    hub = SharedInfraResult(
        entity_id="D-301",
        infrastructure_id="IP-OFFICE",
        infrastructure_type="IPAddress",
        connected_accounts=[f"D-{i}" for i in range(2, 42)],
        is_hub=True,
    )
    result = score_investigation("D-201", [household], [])
    assert result.tier == "NO_ACTION"
    assert score_investigation("D-301", [hub], []).tier == "NO_ACTION"
    explanation = explain_non_escalation("D-201", [household], "2026-10-v1")
    assert "HOUSEHOLD_MITIGATOR" in explanation["signals_triggered"]


def test_all_v2_positive_and_mitigator_signals_use_stored_records():
    path = MoneyPathResult(
        source_id="A-1",
        target_id="BAD-1",
        path_nodes=["A-1", "A-2", "BAD-1"],
        amounts=[100.0, 98.0],
        timestamps=[100, 200],
        is_time_ordered=True,
        time_window_seconds=1000,
        target_confirmed_bad=True,
    )
    result = score_evidence(
        "A-1",
        [
            path,
            {"kind": "PAYROLL_FAN_OUT", "data": {"has_return_flow": False}},
            {"kind": "SHARED_INFRA", "data": {"infrastructure_type": "IPAddress", "infrastructure_id": "IP-1", "connected_accounts": ["A-2", "A-3"]}},
        ],
    )
    assert {signal["rule"] for signal in result.signals} >= {
        "RAPID_PASS_THROUGH",
        "CONFIRMED_BAD_PROXIMITY",
        "PAYROLL_FAN_OUT",
        "SHARED_IP_CLUSTER",
    }
