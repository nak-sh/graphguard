"""Safe, graph-backed action execution and rollback.

FalkorDB is deliberately the source of truth for account state, idempotency,
incident limits, and audit events.  The pure helpers in ``contracts`` and
``policy`` make the state semantics testable without requiring a running DB.
"""

from __future__ import annotations

import inspect
import json
import time
import uuid
from collections.abc import Mapping
from typing import Any, Callable, Dict, Iterable, Optional

try:  # Keep pure action tests runnable when FalkorDB is not installed.
    from falkordb import FalkorDB
except ImportError:  # pragma: no cover - exercised by environments without DB deps
    FalkorDB = None

from apps.actions.contracts import (
    StateSnapshot,
    event_hash,
    real_state_diff,
    rollback_state_decision,
    target_status,
)
from apps.actions.policy import check_incident_limits, validate_policy_tier
from mock_gateway import MockGateway


class ActionConflictError(RuntimeError):
    """Raised only by callers that opt into exception-style conflicts."""


def _rows(result: Any) -> list:
    rows = getattr(result, "result_set", result)
    return list(rows or [])


def _first_value(row: Any, default: Any = None) -> Any:
    if isinstance(row, Mapping):
        return next(iter(row.values()), default)
    if isinstance(row, (list, tuple)):
        return row[0] if row else default
    return row if row is not None else default


class ActionExecutor:
    """Execute reversible actions against Account nodes in FalkorDB.

    ``graph`` is injectable for focused tests, but no state is kept in this
    class: all durable lookups and writes go through the supplied graph.
    """

    def __init__(
        self,
        host: str = "localhost",
        port: int = 6379,
        graph_name: str = "graphguard",
        *,
        graph: Any = None,
        gateway: Any = None,
        policy_validator: Optional[Callable[..., Any]] = None,
        policy_hook: Optional[Callable[..., Any]] = None,
        proposed_action_hook: Optional[Callable[..., Any]] = None,
        proposed_action_linker: Optional[Callable[..., Any]] = None,
        incident_link_hook: Optional[Callable[..., Any]] = None,
        incident_linker: Optional[Callable[..., Any]] = None,
        linkage_hook: Optional[Callable[..., Any]] = None,
        incident_action_cap: Optional[int] = None,
        max_actions_per_incident: Optional[int] = None,
        action_cap: Optional[int] = None,
        incident_cooldown_seconds: Optional[float] = None,
        cooldown_seconds: Optional[float] = None,
        cooldown: Optional[float] = None,
        clock: Callable[[], float] = time.time,
        actor: str = "graphguard",
        require_incident: bool = False,
    ) -> None:
        self.db = None
        if graph is not None:
            self.g = graph
        else:
            if FalkorDB is None:
                raise RuntimeError(
                    "FalkorDB is required for ActionExecutor; install requirements "
                    "or inject a graph for pure tests"
                )
            self.db = FalkorDB(host=host, port=port)
            self.g = self.db.select_graph(graph_name)
        self.gateway = gateway if gateway is not None else MockGateway()
        self.policy_validator = policy_validator or policy_hook or validate_policy_tier
        self.proposed_action_hook = proposed_action_hook or proposed_action_linker
        self.incident_link_hook = incident_link_hook or incident_linker
        self.linkage_hook = linkage_hook
        self.incident_action_cap = (
            incident_action_cap
            if incident_action_cap is not None
            else (
                max_actions_per_incident
                if max_actions_per_incident is not None
                else action_cap
            )
        )
        self.incident_cooldown_seconds = (
            incident_cooldown_seconds
            if incident_cooldown_seconds is not None
            else (cooldown_seconds if cooldown_seconds is not None else cooldown)
        )
        self.clock = clock
        self.actor = actor
        self.require_incident = require_incident

    def _query(self, query: str, params: Optional[Dict[str, Any]] = None) -> list:
        return _rows(self.g.query(query, params or {}))

    def _read_state(self, entity_id: str) -> Optional[StateSnapshot]:
        query = """
        MATCH (a:Account {id: $entity_id})
        RETURN a.status, properties(a)
        """
        rows = self._query(query, {"entity_id": entity_id})
        if not rows:
            return None
        row = rows[0]
        status, properties = None, {}
        if isinstance(row, Mapping):
            status = row.get("a.status", row.get("status"))
            properties = row.get("properties(a)", row.get("properties", {})) or {}
        elif isinstance(row, (list, tuple)):
            status = row[0] if row else None
            if len(row) > 1 and isinstance(row[1], Mapping):
                properties = dict(row[1])
        else:
            status = row
        properties = dict(properties or {})
        if status is None:
            status = properties.get("status")
        return StateSnapshot(entity_id, status, properties)

    def _find_idempotent_event(self, idempotency_key: str) -> Optional[Dict[str, Any]]:
        rows = self._query(
            """
            MATCH (ev:AuditEvent {idempotency_key: $idempotency_key})
            RETURN properties(ev)
            ORDER BY ev.ts DESC LIMIT 1
            """,
            {"idempotency_key": idempotency_key},
        )
        if not rows:
            return None
        row = rows[0]
        if isinstance(row, Mapping):
            return dict(row.get("properties(ev)", row.get("properties", row)))
        if isinstance(row, (list, tuple)) and row and isinstance(row[0], Mapping):
            return dict(row[0])
        return None

    def _find_latest_hash(self) -> str:
        rows = self._query(
            "MATCH (ev:AuditEvent) WHERE ev.event_hash IS NOT NULL "
            "RETURN ev.event_hash ORDER BY ev.chain_index DESC, ev.ts DESC LIMIT 1"
        )
        if not rows:
            return "GENESIS"
        value = _first_value(rows[0], "GENESIS")
        return str(value or "GENESIS")

    def _next_chain_index(self) -> int:
        rows = self._query("MATCH (ev:AuditEvent) RETURN count(ev)")
        return int(_first_value(rows[0], 0) or 0) + 1 if rows else 1

    def _incident_timestamps(self, incident_id: str) -> Iterable[float]:
        rows = self._query(
            """
            MATCH (ev:AuditEvent {incident_id: $incident_id})
            WHERE ev.action <> 'ROLLBACK'
            RETURN ev.ts
            ORDER BY ev.ts ASC
            """,
            {"incident_id": incident_id},
        )
        for row in rows:
            value = _first_value(row)
            if value is not None:
                yield float(value)

    @staticmethod
    def _hook_result_allowed(result: Any) -> bool:
        if result is None:
            return True
        if isinstance(result, bool):
            return result
        if isinstance(result, Mapping):
            return bool(result.get("allowed", result.get("success", True)))
        return bool(getattr(result, "allowed", result))

    @staticmethod
    def _invoke_hook(hook: Optional[Callable[..., Any]], payload: Dict[str, Any]) -> Any:
        if hook is None:
            return True
        if not callable(hook) and callable(getattr(hook, "link", None)):
            hook = hook.link
        # Named arguments are the stable contract. Restricting kwargs to the
        # hook's declared parameters also supports small test hooks such as
        # ``lambda action, incident_id: ...``.
        try:
            signature = inspect.signature(hook)
            parameters = signature.parameters.values()
            accepts_kwargs = any(p.kind == inspect.Parameter.VAR_KEYWORD for p in parameters)
            if accepts_kwargs:
                return hook(**payload)
            accepted = {
                name: value
                for name, value in payload.items()
                if name in signature.parameters
            }
            if accepted:
                return hook(**accepted)
        except (TypeError, ValueError):
            # Builtins and callable objects without inspectable signatures
            # use the positional compatibility path below.
            pass
        try:
            return hook(payload)
        except TypeError:
            try:
                return hook(payload.get("action"))
            except TypeError:
                return hook(
                    payload.get("action"),
                    payload.get("incident_id"),
                    payload.get("proposed_action_id"),
                )

    def _validate_policy(self, action: Dict[str, Any], tier: Optional[str]) -> bool:
        hook = self.policy_validator
        if hook is validate_policy_tier:
            return validate_policy_tier(
                action.get("type", action.get("action_type", "")), tier
            )
        payload = {
            "action": action,
            "action_type": action.get("type", action.get("action_type")),
            "policy_tier": tier,
            "tier": tier,
        }
        result = self._invoke_hook(hook, payload)
        return self._hook_result_allowed(result)

    def _validate_stored_incident_action(
        self,
        *,
        incident_id: Optional[str],
        proposed_action_id: Optional[str],
        entity_id: str,
        action_type: str,
    ) -> tuple[bool, Optional[str], Optional[Dict[str, Any]], Optional[str]]:
        """Validate client intent against the persisted incident proposal."""

        if not incident_id:
            if self.require_incident:
                return False, None, None, "incident_id is required"
            return True, None, None, None
        rows = self._query(
            "MATCH (incident:Incident {id: $incident_id}) RETURN properties(incident) LIMIT 1",
            {"incident_id": incident_id},
        )
        if not rows:
            return False, None, None, "stored incident not found"
        row = rows[0]
        if isinstance(row, Mapping):
            incident = dict(row.get("properties(incident)", row.get("properties", row)))
        elif isinstance(row, (list, tuple)) and row and isinstance(row[0], Mapping):
            incident = dict(row[0])
        else:
            return False, None, None, "stored incident is malformed"
        try:
            proposals = json.loads(incident.get("proposed_actions_json", "[]"))
        except (TypeError, json.JSONDecodeError):
            proposals = []
        match = None
        for candidate in proposals if isinstance(proposals, list) else []:
            if not isinstance(candidate, Mapping):
                continue
            if proposed_action_id and candidate.get("action_id") != proposed_action_id:
                continue
            if candidate.get("target_entity") != entity_id:
                continue
            if str(candidate.get("type", "")).upper() != str(action_type).upper():
                continue
            match = dict(candidate)
            break
        if match is None:
            return False, None, incident, "action was not proposed by the stored incident"
        tier = str(match.get("tier", incident.get("tier", "")))
        approval_status = str(incident.get("approval_status", "NOT_REQUIRED")).upper()
        if approval_status in {"PENDING", "REJECTED"}:
            return False, tier, incident, f"incident approval status is {approval_status.lower()}"
        if approval_status not in {"APPROVED", "NOT_REQUIRED", "AUTO"}:
            return False, tier, incident, "incident approval status is not executable"
        if not self._validate_policy({"type": action_type}, tier):
            return False, tier, incident, "stored action policy tier rejected"
        return True, tier, incident, None

    def dry_run_action(
        self,
        action: Dict[str, Any],
        *,
        policy_tier: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Read current FalkorDB state and return a real-state diff only."""
        action = dict(action)
        entity_id = action.get("target_entity", action.get("entity_id"))
        action_type = action.get("type", action.get("action_type"))
        snapshot = self._read_state(entity_id)
        if snapshot is None:
            return {"success": False, "error": "Entity not found", "entity_id": entity_id}
        if not self._validate_policy(action, policy_tier or action.get("tier")):
            return {"success": False, "error": "Policy tier rejected", "entity_id": entity_id}
        try:
            diff = real_state_diff(
                snapshot, action_type, policy_tier=policy_tier or action.get("tier")
            )
        except ValueError as exc:
            return {"success": False, "error": str(exc), "entity_id": entity_id}
        return {
            "success": True,
            "dry_run": True,
            "entity_id": entity_id,
            # Keep both names: ``diff`` is convenient for service callers,
            # while ``dry_run_diff`` matches the investigation workflow.
            "diff": diff,
            "dry_run_diff": diff,
            "previous_state": diff["previous_state"],
            "proposed_state": diff["proposed_state"],
        }

    # Common naming for callers that call the preview a plan.
    preview_action = dry_run_action

    def lookup_idempotency(self, idempotency_key: str) -> Optional[Dict[str, Any]]:
        """Expose the durable lookup for approval/workflow integrations."""
        return self._find_idempotent_event(idempotency_key)

    def _gateway_action(
        self,
        action_type: str,
        entity_id: str,
        idempotency_key: str,
        incident_id: Optional[str],
        action: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        if action_type.upper() in {"APPLY_HOLD", "HOLD"}:
            return self.gateway.hold(
                entity_id,
                idempotency_key=idempotency_key,
                incident_id=incident_id,
                metadata=action,
            )
        if action_type.upper() in {"RELEASE_HOLD", "RELEASE", "REMOVE_HOLD"}:
            return self.gateway.release(
                entity_id,
                idempotency_key=idempotency_key,
                incident_id=incident_id,
                metadata=action,
            )
        return None

    def _gateway_rollback(
        self,
        original_action: str,
        entity_id: str,
        audit_id: str,
        incident_id: Optional[str],
    ) -> Optional[Dict[str, Any]]:
        """Undo the provider-side operation when the original used one."""
        action = str(original_action or "").upper()
        key = f"ROLLBACK:{audit_id}"
        if action in {"APPLY_HOLD", "HOLD"}:
            return self.gateway.release(
                entity_id, idempotency_key=key, incident_id=incident_id,
                metadata={"rolled_back_audit_id": audit_id},
            )
        if action in {"RELEASE_HOLD", "RELEASE", "REMOVE_HOLD"}:
            return self.gateway.hold(
                entity_id, idempotency_key=key, incident_id=incident_id,
                metadata={"rolled_back_audit_id": audit_id},
            )
        return None

    def execute_action(
        self,
        action: Dict[str, Any],
        idempotency_key: Optional[str] = None,
        *,
        incident_id: Optional[str] = None,
        proposed_action_id: Optional[str] = None,
        policy_tier: Optional[str] = None,
        dry_run: bool = False,
        actor: Optional[str] = None,
    ) -> Dict[str, Any]:
        action = dict(action)
        entity_id = action.get("target_entity", action.get("entity_id"))
        action_type = action.get("type", action.get("action_type"))
        incident_id = incident_id or action.get("incident_id", action.get("alert_id"))
        proposed_action_id = proposed_action_id or action.get("proposed_action_id", action.get("action_id"))
        policy_tier = policy_tier or action.get("policy_tier", action.get("tier"))
        idempotency_key = idempotency_key or action.get("idempotency_key")
        if not idempotency_key:
            idempotency_key = f"IDEM-{uuid.uuid4().hex}"
        if not entity_id or not action_type:
            return {"success": False, "error": "target_entity and type are required"}

        # Durable idempotency lookup occurs before any gateway or graph mutation.
        existing = self._find_idempotent_event(idempotency_key)
        if existing:
            same_request = (
                existing.get("entity_id") == entity_id
                and str(existing.get("action", "")).upper() == str(action_type).upper()
            )
            if not same_request:
                return {
                    "success": False,
                    "conflict": True,
                    "error": "idempotency key belongs to another action",
                    "idempotency_key": idempotency_key,
                }
            return {
                "success": True,
                "idempotent": True,
                "entity_id": entity_id,
                "audit_id": existing.get("id"),
                "verified_status": existing.get("new_state"),
                "idempotency_key": idempotency_key,
            }

        stored_ok, stored_tier, stored_incident, stored_error = self._validate_stored_incident_action(
            incident_id=incident_id,
            proposed_action_id=proposed_action_id,
            entity_id=str(entity_id),
            action_type=str(action_type),
        )
        if not stored_ok:
            return {
                "success": False,
                "error": stored_error or "stored incident validation failed",
                "incident_id": incident_id,
                "proposed_action_id": proposed_action_id,
            }
        policy_tier = stored_tier or policy_tier

        if dry_run or action.get("dry_run"):
            return self.dry_run_action(action, policy_tier=policy_tier)
        if not self._validate_policy(action, policy_tier):
            return {"success": False, "error": "Policy tier rejected", "policy_tier": policy_tier}

        # Redis/FalkorDB stores floating-point properties with a shorter
        # decimal representation. Use integer epoch milliseconds so the
        # serialized audit payload is byte-for-byte stable after a round trip.
        now = int(self.clock() * 1000)
        if incident_id and (
            self.incident_action_cap is not None or self.incident_cooldown_seconds is not None
        ):
            limit = check_incident_limits(
                self._incident_timestamps(incident_id),
                now=now,
                cap=self.incident_action_cap,
                cooldown_seconds=self.incident_cooldown_seconds,
            )
            if not limit.allowed:
                return {
                    "success": False,
                    "error": limit.reason,
                    "incident_id": incident_id,
                    "incident_action_count": limit.count,
                    "last_action_ts": limit.last_ts,
                }

        snapshot = self._read_state(entity_id)
        if snapshot is None:
            return {"success": False, "error": "Entity not found", "entity_id": entity_id}
        try:
            new_status = target_status(action_type)
        except ValueError as exc:
            return {"success": False, "error": str(exc), "entity_id": entity_id}

        linkage_payload = {
            "action": action,
            "proposed_action": action,
            "incident_id": incident_id,
            "incident": incident_id,
            "proposed_action_id": proposed_action_id,
            "idempotency_key": idempotency_key,
        }
        for hook in (self.proposed_action_hook, self.incident_link_hook, self.linkage_hook):
            if not self._hook_result_allowed(self._invoke_hook(hook, linkage_payload)):
                return {"success": False, "error": "Action linkage rejected"}

        gateway_result = self._gateway_action(
            action_type, entity_id, idempotency_key, incident_id, action
        )
        if gateway_result is not None and not self._hook_result_allowed(gateway_result):
            return {"success": False, "error": gateway_result.get("error", "Gateway rejected action")}

        audit_id = f"AUDIT-{uuid.uuid4().hex}"
        previous_hash = self._find_latest_hash()
        event = {
            "id": audit_id,
            "chain_index": self._next_chain_index(),
            # Preserve sub-second ordering so two actions in one second still
            # have a deterministic order in the durable hash chain.
            "ts": now,
            "actor": actor or self.actor,
            "action": str(action_type).upper(),
            "entity_id": entity_id,
            "prev_state": snapshot.status,
            "new_state": new_status,
            "idempotency_key": idempotency_key,
            "pre_state_json": json.dumps(dict(snapshot.properties), sort_keys=True, default=str),
            "prev_hash": previous_hash,
        }
        if incident_id is not None:
            event["incident_id"] = incident_id
        if proposed_action_id is not None:
            event["proposed_action_id"] = proposed_action_id
        event["event_hash"] = event_hash(event, previous_hash)

        optional_event_properties = ""
        if incident_id is not None:
            optional_event_properties += "incident_id: $incident_id,"
        if proposed_action_id is not None:
            optional_event_properties += "proposed_action_id: $proposed_action_id,"

        mutate_query = f"""
        MATCH (a:Account {{id: $entity_id}})
        SET a.status = $new_status
        CREATE (ev:AuditEvent {{
            id: $audit_id, chain_index: $chain_index, ts: $ts, actor: $actor, action: $action_type,
            entity_id: $entity_id, prev_state: $prev_status,
            new_state: $new_status, idempotency_key: $idempotency_key,
            {optional_event_properties}
            pre_state_json: $pre_state_json, prev_hash: $prev_hash,
            event_hash: $event_hash
        }})
        CREATE (ev)-[:TARGETED]->(a)
        """
        # Keep the persisted event's canonical names separate from the Cypher
        # parameter names; this also makes the pre-state that was hashed
        # exactly the state represented in the mutation.
        mutation_params = dict(event)
        mutation_params.update({
            "audit_id": audit_id,
            "action_type": str(action_type).upper(),
            "prev_status": snapshot.status,
            "new_status": new_status,
        })
        self.g.query(mutate_query, mutation_params)
        verified = self._read_state(entity_id)
        actual_status = verified.status if verified else None
        return {
            "success": actual_status == new_status,
            "entity_id": entity_id,
            "audit_id": audit_id,
            "verified_status": actual_status,
            "pre_state": dict(snapshot.properties),
            "idempotency_key": idempotency_key,
            "event_hash": event["event_hash"],
            "gateway": gateway_result,
        }

    def _fetch_audit(self, audit_id: str) -> Optional[Dict[str, Any]]:
        rows = self._query(
            """
            MATCH (ev:AuditEvent {id: $audit_id})-[:TARGETED]->(a:Account)
            RETURN properties(ev), a.id, a.status
            """,
            {"audit_id": audit_id},
        )
        if not rows:
            return None
        row = rows[0]
        if isinstance(row, Mapping):
            event = dict(row.get("properties(ev)", row.get("properties", row)))
            event.setdefault("entity_id", row.get("a.id", row.get("entity_id")))
            event.setdefault("current_status", row.get("a.status", row.get("status")))
            return event
        if isinstance(row, (list, tuple)):
            if row and isinstance(row[0], Mapping):
                event = dict(row[0])
                if len(row) > 1:
                    event.setdefault("entity_id", row[1])
                if len(row) > 2:
                    event.setdefault("current_status", row[2])
                return event
            # Compatibility with the original executor's three-column query.
            if len(row) >= 3:
                return {"prev_state": row[0], "entity_id": row[1],
                        "action": row[2], "current_status": None}
        return None

    def _find_rollback(self, audit_id: str) -> Optional[Dict[str, Any]]:
        rows = self._query(
            """
            MATCH (ev:AuditEvent {rolled_back_audit_id: $audit_id})
            RETURN properties(ev)
            ORDER BY ev.ts DESC LIMIT 1
            """,
            {"audit_id": audit_id},
        )
        if not rows:
            return None
        row = rows[0]
        if isinstance(row, Mapping):
            return dict(row.get("properties(ev)", row.get("properties", row)))
        if isinstance(row, (list, tuple)) and row and isinstance(row[0], Mapping):
            return dict(row[0])
        return None

    def rollback_action(self, audit_id: str, *, actor: Optional[str] = None) -> Dict[str, Any]:
        """Restore only when the account still has the action's post-state.

        A changed current state is reported as a conflict rather than being
        overwritten. A recorded rollback is replayed idempotently.
        """
        previous_rollback = self._find_rollback(audit_id)
        if previous_rollback:
            return {
                "success": True,
                "idempotent": True,
                "entity_id": previous_rollback.get("entity_id"),
                "audit_id": previous_rollback.get("id"),
                "verified_status": previous_rollback.get("new_state"),
            }

        original = self._fetch_audit(audit_id)
        if not original:
            return {"success": False, "error": "Audit event not found"}
        entity_id = original.get("entity_id")
        previous_status = original.get("prev_state")
        expected_status = original.get("new_state")
        current_status = original.get("current_status")
        if current_status is None:
            snapshot = self._read_state(entity_id)
            current_status = snapshot.status if snapshot else None
        if entity_id is None or current_status is None:
            return {"success": False, "error": "Target entity not found"}
        decision = rollback_state_decision(
            current_status, expected_status, previous_status
        )
        if not decision.can_apply:
            return {
                "success": False,
                "idempotent": decision.idempotent,
                "conflict": decision.conflict,
                "error": decision.reason,
                "entity_id": entity_id,
                "verified_status": current_status,
                **({"expected_status": expected_status} if not decision.idempotent else {}),
            }

        gateway_result = self._gateway_rollback(
            original.get("action", ""), entity_id, audit_id, original.get("incident_id")
        )
        if gateway_result is not None and not self._hook_result_allowed(gateway_result):
            return {
                "success": False,
                "error": gateway_result.get("error", "Gateway rejected rollback"),
                "entity_id": entity_id,
            }

        now = int(self.clock() * 1000)
        rollback_id = f"ROLLBACK-{uuid.uuid4().hex}"
        previous_hash = self._find_latest_hash()
        rollback_event = {
            "id": rollback_id,
            "chain_index": self._next_chain_index(),
            "ts": now,
            "actor": actor or self.actor,
            "action": "ROLLBACK",
            "entity_id": entity_id,
            "prev_state": current_status,
            "new_state": previous_status,
            "rolled_back_audit_id": audit_id,
            "idempotency_key": f"ROLLBACK:{audit_id}",
            "prev_hash": previous_hash,
        }
        rollback_event["event_hash"] = event_hash(rollback_event, previous_hash)
        restore_query = """
        MATCH (a:Account {id: $entity_id})
        SET a.status = $new_state
        CREATE (ev:AuditEvent {
            id: $rollback_id, chain_index: $chain_index, ts: $ts, actor: $actor, action: 'ROLLBACK',
            entity_id: $entity_id, prev_state: $prev_state,
            new_state: $new_state, rolled_back_audit_id: $audit_id,
            idempotency_key: $idempotency_key, prev_hash: $prev_hash,
            event_hash: $event_hash
        })
        CREATE (ev)-[:TARGETED]->(a)
        """
        self.g.query(restore_query, {
            "entity_id": entity_id, "new_state": previous_status,
            "rollback_id": rollback_id, "ts": now,
            "chain_index": rollback_event["chain_index"], "actor": actor or self.actor, "prev_state": current_status,
            "audit_id": audit_id, "idempotency_key": f"ROLLBACK:{audit_id}",
            "prev_hash": previous_hash, "event_hash": rollback_event["event_hash"],
        })
        verified = self._read_state(entity_id)
        actual_status = verified.status if verified else None
        return {
            "success": actual_status == previous_status,
            "entity_id": entity_id,
            "audit_id": rollback_id,
            "verified_status": actual_status,
            "event_hash": rollback_event["event_hash"],
            "gateway": gateway_result,
        }

    rollback = rollback_action

    def audit_events(self) -> list[Dict[str, Any]]:
        """Read the persisted event chain in its durable order."""
        rows = self._query(
            "MATCH (ev:AuditEvent) WHERE ev.event_hash IS NOT NULL "
            "RETURN properties(ev) ORDER BY ev.chain_index ASC, ev.ts ASC"
        )
        events = []
        for row in rows:
            if isinstance(row, Mapping):
                events.append(dict(row.get("properties(ev)", row.get("properties", row))))
            elif isinstance(row, (list, tuple)) and row and isinstance(row[0], Mapping):
                events.append(dict(row[0]))
        return events

    def verify_audit_chain(self) -> bool:
        from apps.actions.contracts import verify_event_chain

        return verify_event_chain(self.audit_events())
