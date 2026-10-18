"""Pure contracts and state semantics for safe graph actions."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, Mapping, Optional


ACTION_STATUS = {
    "APPLY_HOLD": "HOLD", "HOLD": "HOLD",
    "RELEASE_HOLD": "ACTIVE", "RELEASE": "ACTIVE", "REMOVE_HOLD": "ACTIVE",
    "FLAG_FOR_REVIEW": "UNDER_REVIEW",
}


@dataclass(frozen=True)
class StateSnapshot:
    entity_id: str
    status: Optional[str]
    properties: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class StateDiff:
    entity_id: str
    previous_state: Mapping[str, Any]
    proposed_state: Mapping[str, Any]
    changes: Mapping[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "entity_id": self.entity_id, "node_label": "Account",
            "previous_state": dict(self.previous_state),
            "proposed_state": dict(self.proposed_state),
            "changes": dict(self.changes),
        }


@dataclass(frozen=True)
class RollbackDecision:
    can_apply: bool
    idempotent: bool = False
    conflict: bool = False
    reason: Optional[str] = None


def rollback_state_decision(
    current_state: Optional[str],
    action_state: Optional[str],
    pre_action_state: Optional[str],
    *,
    already_recorded: bool = False,
) -> RollbackDecision:
    """Pure compare-and-restore semantics used before a graph mutation."""

    if already_recorded:
        return RollbackDecision(can_apply=False, idempotent=True)
    if current_state == action_state:
        return RollbackDecision(can_apply=True)
    if current_state == pre_action_state:
        return RollbackDecision(
            can_apply=False,
            conflict=True,
            reason="state is already pre-action without a rollback audit",
        )
    return RollbackDecision(
        can_apply=False,
        conflict=True,
        reason="state changed after action; rollback not applied",
    )


def target_status(action_type: str) -> str:
    try:
        return ACTION_STATUS[action_type.upper()]
    except KeyError as exc:
        raise ValueError(f"unsupported action type: {action_type}") from exc


def real_state_diff(snapshot: StateSnapshot, action_type: str,
                    *, policy_tier: Optional[str] = None) -> Dict[str, Any]:
    """Build a dry-run diff from the captured graph state."""
    new_status = target_status(action_type)
    previous = dict(snapshot.properties)
    previous.setdefault("status", snapshot.status)
    proposed = dict(previous)
    proposed["status"] = new_status
    changes = {
        key: {"from": previous.get(key), "to": proposed.get(key)}
        for key in proposed if previous.get(key) != proposed.get(key)
    }
    diff = StateDiff(snapshot.entity_id, previous, proposed, changes).to_dict()
    if policy_tier is not None:
        diff["policy_tier"] = policy_tier
    return diff


def canonical_event_payload(event: Mapping[str, Any]) -> str:
    return json.dumps(dict(event), sort_keys=True, separators=(",", ":"), default=str)


def event_hash(event: Mapping[str, Any], previous_hash: str = "GENESIS") -> str:
    payload = dict(event)
    payload.pop("event_hash", None)
    payload["prev_hash"] = previous_hash
    return hashlib.sha256(canonical_event_payload(payload).encode("utf-8")).hexdigest()


def verify_event_chain(events: Iterable[Mapping[str, Any]]) -> bool:
    previous = "GENESIS"
    for item in events:
        expected = event_hash(item, previous)
        if item.get("prev_hash") != previous or item.get("event_hash") != expected:
            return False
        previous = expected
    return True
