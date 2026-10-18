"""Focused v2 integration checks for the real FalkorDB-backed flow."""

import socket
import uuid

import pytest
from fastapi.testclient import TestClient

from apps.agent.workflow import InvestigationWorkflow
from apps.api.main import app
from apps.graph_tools.tools import GraphTools


def _require_db() -> None:
    sock = socket.socket()
    sock.settimeout(0.5)
    try:
        if sock.connect_ex(("127.0.0.1", 6379)) != 0:
            pytest.skip("FalkorDB is not reachable on localhost:6379")
    finally:
        sock.close()


def test_workflow_targets_all_ring_accounts_and_grounds_report():
    _require_db()
    result = InvestigationWorkflow().run("ALERT-104", "A-104")
    assert result["tier"] == "AUTO_HOLD"
    assert {action["target_entity"] for action in result["proposed_actions"]} == {"A-104", "A-105", "A-106", "A-107", "A-108"}
    assert len(result["dry_run_diff"]["actions"]) == 5
    assert all(diff["changes"]["status"]["from"] == "ACTIVE" for diff in result["dry_run_diff"]["actions"])
    assert result["grounding"]["grounded"] is True


def test_ip_hub_and_neighborhood_deduplication_are_graph_backed():
    _require_db()
    tools = GraphTools()
    ip_results = tools.find_shared_ips("D3-001")
    assert ip_results and ip_results[0].is_hub and ip_results[0].hub_degree == 40
    neighborhood = tools.get_neighborhood("A-104", max_hops=4, limit=200)
    edge_keys = {(edge.source, edge.target, edge.relationship, edge.properties.get("id")) for edge in neighborhood.edges}
    assert len(edge_keys) == len(neighborhood.edges)
    assert all(node.id not in neighborhood.hub_nodes for node in neighborhood.nodes)


def test_api_enforces_stored_incident_approval_and_idempotency():
    _require_db()
    client = TestClient(app)
    investigation = client.post("/api/investigate", json={"alert_id": "ALERT-104", "entity_id": "A-104"})
    assert investigation.status_code == 200
    state = investigation.json()
    action = state["proposed_actions"][0]
    incident_id = state["incident_id"]
    assert client.post("/api/actions/dry-run", json={"incident_id": incident_id, "proposed_action_id": action["action_id"]}).status_code == 200
    payload = {"incident_id": incident_id, "proposed_action_id": action["action_id"], "target_entity": action["target_entity"], "type": action["type"], "idempotency_key": f"TEST-V2-IDEM-{uuid.uuid4().hex}"}
    assert client.post("/api/actions/execute", json=payload).status_code == 409
    assert client.post(f"/api/incidents/{incident_id}/approval", json={"approved": True}).status_code == 200
    first = client.post("/api/actions/execute", json=payload)
    assert first.status_code == 200 and first.json()["success"] is True
    replay = client.post("/api/actions/execute", json=payload)
    assert replay.status_code == 200 and replay.json()["idempotent"] is True
    rollback = client.post("/api/actions/rollback", json={"audit_id": first.json()["audit_id"]})
    assert rollback.status_code == 200 and rollback.json()["success"] is True
    repeated = client.post("/api/actions/rollback", json={"audit_id": first.json()["audit_id"]})
    assert repeated.status_code == 200 and repeated.json()["idempotent"] is True
    assert client.get("/api/audit/verify").json()["valid"] is True


def test_sse_stream_emits_progress_and_completion():
    _require_db()
    client = TestClient(app)
    response = client.get("/api/investigate/stream?alert_id=ALERT-D201&entity_id=D-201")
    assert response.status_code == 200
    assert "tool_completed" in response.text
    assert "investigation_complete" in response.text
