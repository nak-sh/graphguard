"""Deterministic, observable mock implementation of the gateway contract.

This models the remote enforcement service, not GraphGuard's durable action
database. Durable action state and audit records remain in FalkorDB.
"""

from __future__ import annotations

import threading
import time
import uuid
from copy import deepcopy
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple


class _RequestLog(list):
    """List view that is also callable for method-style consumers."""

    def __call__(self) -> List[Dict[str, Any]]:
        return deepcopy(self)


@dataclass(frozen=True)
class GatewayResult:
    success: bool
    operation: str
    entity_id: str
    status: str
    request_id: str
    idempotency_key: str
    idempotent: bool = False
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "operation": self.operation,
            "entity_id": self.entity_id,
            "status": self.status,
            "request_id": self.request_id,
            "idempotency_key": self.idempotency_key,
            "idempotent": self.idempotent,
            **({"error": self.error} if self.error else {}),
        }


class MockGateway:
    """Idempotent hold/release provider with a visible request log."""

    def __init__(self, *, clock=time.time) -> None:
        self._clock = clock
        self._lock = threading.RLock()
        self._state: Dict[str, str] = {}
        self._responses: Dict[str, Tuple[str, str, Dict[str, Any]]] = {}
        self._log: List[Dict[str, Any]] = []

    def _request(self, operation: str, entity_id: str, *,
                 idempotency_key: str, incident_id: Optional[str],
                 metadata: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        if not idempotency_key:
            raise ValueError("idempotency_key is required")
        with self._lock:
            now = self._clock()
            previous = self._responses.get(idempotency_key)
            if previous is not None:
                previous_operation, previous_entity, previous_result = previous
                if (previous_operation, previous_entity) != (operation, entity_id):
                    result = GatewayResult(
                        success=False, operation=operation, entity_id=entity_id,
                        status=self._state.get(entity_id, "UNKNOWN"),
                        request_id=f"GW-{uuid.uuid4().hex[:12]}",
                        idempotency_key=idempotency_key,
                        error="idempotency key already belongs to another request",
                    ).to_dict()
                else:
                    result = dict(previous_result)
                    result["idempotent"] = True
                    result["replayed_at"] = now
                self._log.append({
                    "ts": now, "operation": operation, "entity_id": entity_id,
                    "idempotency_key": idempotency_key, "incident_id": incident_id,
                    "metadata": deepcopy(metadata or {}),
                    "replayed": bool(result.get("idempotent")),
                    "result": deepcopy(result),
                })
                return result

            status = "HOLD" if operation == "hold" else "ACTIVE"
            self._state[entity_id] = status
            result = GatewayResult(
                success=True, operation=operation, entity_id=entity_id,
                status=status, request_id=f"GW-{uuid.uuid4().hex[:12]}",
                idempotency_key=idempotency_key,
            ).to_dict()
            self._responses[idempotency_key] = (operation, entity_id, dict(result))
            self._log.append({
                "ts": now, "operation": operation, "entity_id": entity_id,
                "idempotency_key": idempotency_key, "incident_id": incident_id,
                "metadata": deepcopy(metadata or {}), "replayed": False,
                "result": deepcopy(result),
            })
            return result

    def hold(self, entity_id: str, *, idempotency_key: str,
             incident_id: Optional[str] = None,
             metadata: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        return self._request("hold", entity_id, idempotency_key=idempotency_key,
                             incident_id=incident_id, metadata=metadata)

    def release(self, entity_id: str, *, idempotency_key: str,
                incident_id: Optional[str] = None,
                metadata: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        return self._request("release", entity_id, idempotency_key=idempotency_key,
                             incident_id=incident_id, metadata=metadata)

    @property
    def request_log(self) -> List[Dict[str, Any]]:
        with self._lock:
            return _RequestLog(deepcopy(self._log))

    @property
    def requests(self) -> List[Dict[str, Any]]:
        return self.request_log

    def get_request_log(self) -> List[Dict[str, Any]]:
        return self.request_log

    def status(self, entity_id: str) -> Optional[str]:
        with self._lock:
            return self._state.get(entity_id)


MockGatewayService = MockGateway
