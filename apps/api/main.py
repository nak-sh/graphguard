from fastapi import FastAPI
from pydantic import BaseModel
from apps.agent.workflow import InvestigationWorkflow
from apps.actions.executor import ActionExecutor

app = FastAPI(title="GraphGuard API")
workflow = InvestigationWorkflow()
executor = ActionExecutor()

class InvestigateRequest(BaseModel):
    alert_id: str
    entity_id: str

class ActionRequest(BaseModel):
    target_entity: str
    type: str  # e.g., "APPLY_HOLD", "FLAG_FOR_REVIEW"

class RollbackRequest(BaseModel):
    audit_id: str

@app.post("/api/investigate")
def investigate(req: InvestigateRequest):
    """Runs the LangGraph workflow and returns the final state (findings & dry-run diff)."""
    return workflow.run(req.alert_id, req.entity_id)

@app.post("/api/actions/execute")
def execute_action(req: ActionRequest):
    """Executes a proposed action, mutating graph state and logging an audit event."""
    action_dict = {"target_entity": req.target_entity, "type": req.type}
    return executor.execute_action(action_dict)

@app.post("/api/actions/rollback")
def rollback_action(req: RollbackRequest):
    """Reverts an action using the previous state stored in the audit trail."""
    return executor.rollback_action(req.audit_id)