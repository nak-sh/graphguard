"""Optional standalone mock payment gateway service."""

from fastapi import FastAPI
from pydantic import BaseModel

from mock_gateway.service import MockGateway


app = FastAPI(title="GraphGuard Mock Payment Gateway", version="1.0.0")
gateway = MockGateway()


class GatewayRequest(BaseModel):
    entity_id: str
    idempotency_key: str
    incident_id: str | None = None


@app.get("/health")
def health() -> dict[str, bool]:
    return {"ok": True}


@app.post("/holds")
def hold(request: GatewayRequest) -> dict:
    return gateway.hold(request.entity_id, idempotency_key=request.idempotency_key, incident_id=request.incident_id)


@app.post("/releases")
def release(request: GatewayRequest) -> dict:
    return gateway.release(request.entity_id, idempotency_key=request.idempotency_key, incident_id=request.incident_id)


@app.get("/requests")
def requests() -> list[dict]:
    return gateway.request_log
