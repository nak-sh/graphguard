"""FastAPI surface for the GraphGuard investigation workspace."""

from __future__ import annotations

import json
import os
import re
import secrets
from pathlib import Path
from typing import Any, Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from apps.actions.executor import ActionExecutor
from apps.agent.workflow import InvestigationWorkflow
from apps.agent.grounding import check_grounding
from apps.graph_tools.tools import GraphTools
from apps.policy.scorer import PolicyModel, load_policy, score_evidence
from apps.signature.containment import optimize_containment
from apps.signature.redteam import red_team_matrix
from apps.signature.replay import replay_transfers


app = FastAPI(title="GraphGuard API", version="2.0.0")

_services: dict[str, Any] = {}
_autonomy_mode = os.getenv("GRAPHGUARD_AUTONOMY_MODE", "APPROVE").upper()


def services() -> tuple[GraphTools, ActionExecutor, InvestigationWorkflow]:
    if not _services:
        host = os.getenv("GRAPHGUARD_DB_HOST", "localhost")
        port = int(os.getenv("GRAPHGUARD_DB_PORT", "6379"))
        graph_name = os.getenv("GRAPHGUARD_GRAPH_NAME", "graphguard")
        tools = GraphTools(host=host, port=port, graph_name=graph_name)
        executor = ActionExecutor(host=host, port=port, graph_name=graph_name, require_incident=True)
        _services.update({"tools": tools, "executor": executor})
        _services["workflow"] = InvestigationWorkflow(host=host, port=port, graph_name=graph_name, tools=tools)
    return _services["tools"], _services["executor"], _services["workflow"]


class InvestigateRequest(BaseModel):
    alert_id: str
    entity_id: str
    pause_for_approval: bool = False
    autonomy_mode: str = "APPROVE"
    thread_id: Optional[str] = None


class ActionRequest(BaseModel):
    incident_id: str
    proposed_action_id: str
    target_entity: str
    type: str
    idempotency_key: Optional[str] = None
    actor: str = "analyst"


class DryRunRequest(BaseModel):
    incident_id: str
    proposed_action_id: str


class ApprovalRequest(BaseModel):
    approved: bool
    actor: str = "analyst"
    approval_token: Optional[str] = None


class RollbackRequest(BaseModel):
    audit_id: str
    actor: str = "analyst"


class AutonomyRequest(BaseModel):
    mode: str = Field(pattern="^(OBSERVE|RECOMMEND|APPROVE|AUTO_WITHIN_LIMITS)$")


class PolicySandboxRequest(BaseModel):
    version: str = "2026-10-sandbox"
    thresholds: dict[str, int] = {}
    weights: dict[str, int] = {}
    incident_ids: list[str] = []


class CopilotRequest(BaseModel):
    incident_id: str
    question: str


@app.get("/health")
def health() -> dict[str, Any]:
    try:
        tools, _, _ = services()
        result = tools.g.query("RETURN 1 AS ok").result_set
        return {"ok": bool(result and result[0][0] == 1), "falkordb": True, "synthetic_data": True}
    except Exception as exc:
        return {"ok": False, "falkordb": False, "synthetic_data": True, "error": str(exc)}


@app.get("/api/alerts")
def list_alerts(status: Optional[str] = Query(default=None)) -> list[dict[str, Any]]:
    return services()[0].get_alerts(status=status)


@app.get("/api/alerts/{alert_id}")
def get_alert(alert_id: str) -> dict[str, Any]:
    value = services()[0].get_alert(alert_id)
    if value is None:
        raise HTTPException(status_code=404, detail="alert not found")
    return value


@app.post("/api/investigate")
def investigate(req: InvestigateRequest) -> dict[str, Any]:
    _, _, workflow = services()
    try:
        return workflow.run(
            req.alert_id,
            req.entity_id,
            pause_for_approval=req.pause_for_approval,
            autonomy_mode=req.autonomy_mode.upper(),
            thread_id=req.thread_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/investigate/stream")
def investigate_stream(alert_id: str, entity_id: str, thread_id: Optional[str] = None) -> StreamingResponse:
    _, _, workflow = services()

    def events():
        try:
            for event in workflow.stream(alert_id, entity_id, thread_id=thread_id):
                yield f"event: {event.get('event', 'progress')}\ndata: {json.dumps(event, default=str)}\n\n"
        except Exception as exc:
            payload = {"event": "error", "error": str(exc)}
            yield f"event: error\ndata: {json.dumps(payload)}\n\n"

    return StreamingResponse(events(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.get("/api/incidents")
def list_incidents() -> list[dict[str, Any]]:
    return services()[0].list_incidents()


@app.get("/api/incidents/{incident_id}")
def get_incident(incident_id: str) -> dict[str, Any]:
    value = services()[0].get_incident(incident_id)
    if value is None:
        raise HTTPException(status_code=404, detail="incident not found")
    return value


@app.get("/api/incidents/{incident_id}/evidence")
def incident_evidence(incident_id: str) -> list[dict[str, Any]]:
    tools = services()[0]
    if tools.get_incident(incident_id) is None:
        raise HTTPException(status_code=404, detail="incident not found")
    return tools.get_incident_evidence(incident_id)


@app.post("/api/incidents/{incident_id}/approval")
def approve_incident(incident_id: str, req: ApprovalRequest) -> dict[str, Any]:
    tools = services()[0]
    incident = tools.get_incident(incident_id)
    if incident is None:
        raise HTTPException(status_code=404, detail="incident not found")
    status = "APPROVED" if req.approved else "REJECTED"
    updated = tools.update_incident(incident_id, {"approval_status": status, "approved_by": req.actor})
    return {"success": True, "incident_id": incident_id, "approval_status": status, "incident": updated}


def _stored_action(incident: dict[str, Any], proposed_action_id: str) -> dict[str, Any]:
    for action in incident.get("proposed_actions", []) or []:
        if action.get("action_id") == proposed_action_id:
            return dict(action)
    raise HTTPException(status_code=400, detail="proposed action not found on incident")


@app.post("/api/actions/dry-run")
def dry_run_action(req: DryRunRequest) -> dict[str, Any]:
    tools, executor, _ = services()
    incident = tools.get_incident(req.incident_id)
    if incident is None:
        raise HTTPException(status_code=404, detail="incident not found")
    action = _stored_action(incident, req.proposed_action_id)
    action["incident_id"] = req.incident_id
    result = executor.dry_run_action(action, policy_tier=action.get("tier"))
    if result.get("success"):
        tools.update_incident(req.incident_id, {"dry_run_completed": True, "dry_run_diff_json": json.dumps(result.get("diff", {}), sort_keys=True)})
    return result


@app.post("/api/actions/execute")
def execute_action(req: ActionRequest) -> dict[str, Any]:
    tools, executor, _ = services()
    if _autonomy_mode in {"OBSERVE", "RECOMMEND"}:
        raise HTTPException(status_code=403, detail=f"autonomy mode {_autonomy_mode} does not permit execution")
    incident = tools.get_incident(req.incident_id)
    if incident is None:
        raise HTTPException(status_code=404, detail="incident not found")
    stored = _stored_action(incident, req.proposed_action_id)
    if stored.get("target_entity") != req.target_entity or str(stored.get("type", "")).upper() != req.type.upper():
        raise HTTPException(status_code=400, detail="request does not match stored proposed action")
    if not incident.get("dry_run_completed") and incident.get("tier") in {"AUTO_HOLD", "MANUAL_REVIEW"}:
        raise HTTPException(status_code=400, detail="dry-run is required before execution")
    key = req.idempotency_key or f"IDEM-{secrets.token_hex(12)}"
    action = dict(stored)
    action.update({"incident_id": req.incident_id, "proposed_action_id": req.proposed_action_id, "idempotency_key": key})
    result = executor.execute_action(action, incident_id=req.incident_id, proposed_action_id=req.proposed_action_id, policy_tier=stored.get("tier"), idempotency_key=key, actor=req.actor)
    if not result.get("success"):
        raise HTTPException(status_code=409, detail=result.get("error", "action rejected"))
    return result


@app.post("/api/actions/rollback")
def rollback_action(req: RollbackRequest) -> dict[str, Any]:
    result = services()[1].rollback_action(req.audit_id, actor=req.actor)
    if not result.get("success"):
        raise HTTPException(status_code=409, detail=result.get("error", "rollback rejected"))
    return result


@app.get("/api/audit")
def audit_events() -> list[dict[str, Any]]:
    return services()[1].audit_events()


@app.get("/api/audit/verify")
def verify_audit() -> dict[str, Any]:
    return {"valid": services()[1].verify_audit_chain()}


@app.post("/api/audit/simulate-tampering")
def simulate_tampering(audit_id: str, field: str = "new_state") -> dict[str, Any]:
    if os.getenv("GRAPHGUARD_DEV_CONTROLS", "0") not in {"1", "true", "TRUE"}:
        raise HTTPException(status_code=403, detail="dev-only control is disabled")
    tools = services()[0]
    result = tools.g.query("MATCH (ev:AuditEvent {id: $audit_id}) SET ev[$field] = 'TAMPERED' RETURN properties(ev)", {"audit_id": audit_id, "field": field}).result_set
    return {"success": bool(result), "audit_id": audit_id, "valid_after": services()[1].verify_audit_chain()}


@app.get("/api/gateway/requests")
def gateway_requests() -> list[dict[str, Any]]:
    return services()[1].gateway.request_log


@app.get("/api/settings/autonomy")
def get_autonomy() -> dict[str, str]:
    return {"mode": _autonomy_mode}


@app.put("/api/settings/autonomy")
def set_autonomy(req: AutonomyRequest) -> dict[str, str]:
    global _autonomy_mode
    _autonomy_mode = req.mode
    return {"mode": _autonomy_mode}


@app.post("/api/policy/sandbox")
def policy_sandbox(req: PolicySandboxRequest) -> dict[str, Any]:
    tools = services()[0]
    base = load_policy()
    raw = base.model_dump()
    raw["version"] = req.version
    raw["thresholds"].update(req.thresholds)
    for name, weight in req.weights.items():
        if name not in raw["signals"]:
            raise HTTPException(status_code=400, detail=f"unknown policy signal: {name}")
        raw["signals"][name]["weight"] = weight
    policy = PolicyModel.model_validate(raw)
    incidents = tools.list_incidents()
    if req.incident_ids:
        incidents = [incident for incident in incidents if incident.get("id") in req.incident_ids]
    rows: list[dict[str, Any]] = []
    for incident in incidents:
        evidence = tools.get_incident_evidence(str(incident["id"]))
        try:
            from apps.graph_tools.models import EvidenceBundle, EvidenceItem
            result = score_evidence(str(incident.get("entity_id")), EvidenceBundle(entity_id=str(incident.get("entity_id")), items=[EvidenceItem.model_validate(item) for item in evidence], policy_version=base.version), policy=policy, policy_version=policy.version)
            rows.append({"incident_id": incident.get("id"), "entity_id": incident.get("entity_id"), "original_tier": incident.get("tier"), "sandbox_score": result.score, "sandbox_tier": result.tier, "regression": str(incident.get("tier")) != result.tier, "decoy_regression": str(incident.get("entity_id", "")).startswith("D-") and result.tier != "NO_ACTION"})
        except Exception as exc:
            rows.append({"incident_id": incident.get("id"), "error": str(exc)})
    return {"policy": policy.model_dump(), "rows": rows, "decoy_regressions": [row for row in rows if row.get("decoy_regression")], "cached_evidence_only": True}


@app.post("/api/policy/sandbox/save")
def save_policy_sandbox(req: PolicySandboxRequest) -> dict[str, Any]:
    if not re.fullmatch(r"[A-Za-z0-9_.-]{1,48}", req.version):
        raise HTTPException(status_code=400, detail="policy version contains unsupported characters")
    base = load_policy()
    raw = base.model_dump()
    raw["version"] = req.version
    raw["thresholds"].update(req.thresholds)
    for name, weight in req.weights.items():
        if name not in raw["signals"]:
            raise HTTPException(status_code=400, detail=f"unknown policy signal: {name}")
        raw["signals"][name]["weight"] = weight
    destination = os.path.join(os.path.dirname(__file__), "..", "policy", f"policy_{req.version}.yaml")
    import yaml
    with open(destination, "w", encoding="utf-8") as handle:
        yaml.safe_dump(raw, handle, sort_keys=False)
    return {"saved": True, "version": req.version, "path": os.path.abspath(destination)}


@app.get("/api/incidents/{incident_id}/why")
def why_explorer(incident_id: str) -> dict[str, Any]:
    tools = services()[0]
    incident = tools.get_incident(incident_id)
    if incident is None:
        raise HTTPException(status_code=404, detail="incident not found")
    evidence = tools.get_incident_evidence(incident_id)
    templates = {
        "detect_transfer_cycles": "MATCH (n0:Account {id: $entity_id})-[r0:SENT_MONEY]->... RETURN bounded cycle evidence",
        "find_shared_infrastructure_device": "MATCH (a:Account {id: $entity_id})-[:USES_DEVICE]->(d:Device)<-[:USES_DEVICE]-(other:Account) RETURN d, other",
        "find_shared_infrastructure_ip": "MATCH (a:Account {id: $entity_id})-[:USED_IP]->(ip:IPAddress)<-[:USED_IP]-(other:Account) RETURN ip, other",
        "trace_money_paths": "MATCH (source:Account {id: $source_id})-[:SENT_MONEY*1..$max_hops]->(target:Account) RETURN bounded path evidence",
    }
    return {"incident": incident, "evidence": [{**item, "cypher_template": templates.get(item.get("query_name"), "Parameterized query recorded in apps/graph_tools/tools.py"), "parameters": {"entity_id": incident.get("entity_id")}} for item in evidence], "grounding": check_grounding(incident.get("summary", ""), evidence).__dict__}


@app.post("/api/copilot")
def copilot(req: CopilotRequest) -> dict[str, Any]:
    tools = services()[0]
    incident = tools.get_incident(req.incident_id)
    if incident is None:
        raise HTTPException(status_code=404, detail="incident not found")
    evidence = tools.get_incident_evidence(req.incident_id)
    citations = ", ".join(f"[{item.get('id')}]" for item in evidence[:4]) or "[no-evidence]"
    question = req.question.lower()
    if "why" in question and "not" in question:
        answer = f"The stored policy result remained below an action threshold or was mitigated by a benign pattern. Review the cited evidence: {citations}."
    elif "cycle" in question:
        answer = f"The cycle conclusion is based only on the stored time-ordered transfer evidence, not on model-created relationships: {citations}."
    else:
        answer = f"This incident is {incident.get('tier', 'unclassified')} at score {incident.get('score', 0)} using stored evidence {citations}. Findings are leads, not proof."
    grounding = check_grounding(answer, evidence)
    if not grounding.grounded:
        return {"blocked": True, "answer": None, "violations": list(grounding.violations)}
    return {"blocked": False, "answer": answer, "citations": [item.get("id") for item in evidence[:4]], "grounding": grounding.__dict__, "offline_mode": True}


@app.get("/api/entities/{entity_id}/neighborhood")
def entity_neighborhood(entity_id: str, max_hops: int = 4, limit: int = 200) -> dict[str, Any]:
    return services()[0].get_neighborhood(entity_id, max_hops=max_hops, limit=limit).model_dump()


@app.get("/api/entities/{entity_id}/replay")
def entity_replay(entity_id: str, limit: int = 500) -> dict[str, Any]:
    tools = services()[0]
    result = tools.g.query(
        "MATCH (a:Account {id: $entity_id})-[r:SENT_MONEY]->(b:Account) RETURN a.id, b.id, properties(r) ORDER BY r.ts LIMIT $limit",
        {"entity_id": entity_id, "limit": limit},
    ).result_set
    edges = [{"source": row[0], "target": row[1], **dict(row[2] or {})} for row in result]
    return replay_transfers(edges, entity_id=entity_id)


@app.get("/api/entities/{entity_id}/containment")
def entity_containment(entity_id: str) -> dict[str, Any]:
    tools = services()[0]
    cycles = tools.detect_transfer_cycles(entity_id, limit=100)
    paths = tools.trace_money_paths(entity_id, max_hops=5, limit=100)
    targets = sorted({entity_id, *[node for cycle in cycles for node in cycle.cycle_nodes], *[node for path in paths for node in path.path_nodes]})
    properties = tools.get_account_states(targets)
    return optimize_containment(cycles, paths, properties)


@app.get("/api/red-team/matrix")
def red_team() -> dict[str, Any]:
    return red_team_matrix()


@app.get("/api/benchmark/latest")
def latest_benchmark() -> dict[str, Any]:
    artifact = Path(__file__).resolve().parents[2] / "artifacts" / "benchmark.json"
    if not artifact.exists():
        raise HTTPException(status_code=404, detail="no benchmark artifact; run make benchmark")
    return json.loads(artifact.read_text(encoding="utf-8"))
