"""Offline tests for safe-action idempotency and rollback semantics."""

from apps.actions.contracts import (
    StateSnapshot,
    event_hash,
    real_state_diff,
    rollback_state_decision,
    verify_event_chain,
)
from apps.actions.policy import check_incident_limits
from mock_gateway import MockGateway


def test_gateway_hold_release_are_idempotent_and_visible():
    gateway = MockGateway(clock=lambda: 100.0)
    first = gateway.hold("A-1", idempotency_key="incident-1")
    replay = gateway.hold("A-1", idempotency_key="incident-1")

    assert first["success"] is True
    assert replay["idempotent"] is True
    assert replay["request_id"] == first["request_id"]
    assert len(gateway.request_log()) == 2
    assert gateway.status("A-1") == "HOLD"

    released = gateway.release("A-1", idempotency_key="incident-1-release")
    assert released["status"] == "ACTIVE"
    assert gateway.status("A-1") == "ACTIVE"


def test_real_state_diff_captures_pre_state_and_hash_chain():
    snapshot = StateSnapshot("A-1", "ACTIVE", {"status": "ACTIVE", "tier": "STANDARD"})
    diff = real_state_diff(snapshot, "APPLY_HOLD", policy_tier="AUTO_HOLD")
    assert diff["previous_state"]["status"] == "ACTIVE"
    assert diff["proposed_state"]["status"] == "HOLD"
    assert diff["changes"]["status"] == {"from": "ACTIVE", "to": "HOLD"}

    first = {"id": "a", "action": "APPLY_HOLD", "prev_state": "ACTIVE", "new_state": "HOLD"}
    first["prev_hash"] = "GENESIS"
    first["event_hash"] = event_hash(first)
    second = {"id": "b", "action": "ROLLBACK", "prev_state": "HOLD", "new_state": "ACTIVE"}
    second["prev_hash"] = first["event_hash"]
    second["event_hash"] = event_hash(second, first["event_hash"])
    assert verify_event_chain([first, second])
    second["new_state"] = "HOLD"
    assert not verify_event_chain([first, second])


def test_incident_cap_and_cooldown_are_pure_and_fail_closed():
    assert not check_incident_limits([90], now=100, cap=1).allowed
    decision = check_incident_limits([99], now=100, cooldown_seconds=5)
    assert not decision.allowed
    assert decision.reason == "incident action cooldown active"
    assert check_incident_limits([90], now=100, cap=2, cooldown_seconds=5).allowed


def test_rollback_state_semantics_are_conflict_aware_and_idempotent():
    assert rollback_state_decision("HOLD", "HOLD", "ACTIVE").can_apply
    conflict = rollback_state_decision("UNDER_REVIEW", "HOLD", "ACTIVE")
    assert conflict.conflict
    assert "state changed" in conflict.reason
    already = rollback_state_decision("ACTIVE", "HOLD", "ACTIVE")
    assert already.conflict
    assert not already.can_apply
    replay = rollback_state_decision("ACTIVE", "HOLD", "ACTIVE", already_recorded=True)
    assert replay.idempotent
