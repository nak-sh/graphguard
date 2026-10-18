"""Pure action lifecycle checks used by evaluation."""

from __future__ import annotations

from apps.actions.contracts import rollback_state_decision
from mock_gateway import MockGateway


def action_lifecycle_check() -> dict[str, bool]:
    gateway = MockGateway()
    first = gateway.hold("A-TEST", idempotency_key="EVAL-1")
    replay = gateway.hold("A-TEST", idempotency_key="EVAL-1")
    rollback = rollback_state_decision("HOLD", "HOLD", "ACTIVE")
    conflict = rollback_state_decision("UNDER_REVIEW", "HOLD", "ACTIVE")
    return {
        "idempotency": bool(first["success"] and replay["success"] and replay["idempotent"] and len(gateway.request_log) == 2),
        "rollback_fidelity": bool(rollback.can_apply and not rollback.idempotent and conflict.conflict),
    }
