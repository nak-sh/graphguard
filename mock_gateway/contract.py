"""Service contract for an enforcement gateway."""

from typing import Any, Dict, List, Optional, Protocol, runtime_checkable


@runtime_checkable
class GatewayService(Protocol):
    def hold(self, entity_id: str, *, idempotency_key: str,
             incident_id: Optional[str] = None,
             metadata: Optional[Dict[str, Any]] = None) -> Dict[str, Any]: ...

    def release(self, entity_id: str, *, idempotency_key: str,
                incident_id: Optional[str] = None,
                metadata: Optional[Dict[str, Any]] = None) -> Dict[str, Any]: ...

    def request_log(self) -> List[Dict[str, Any]]: ...
