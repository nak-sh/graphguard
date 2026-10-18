from typing import TypedDict, List, Dict, Any, Optional

class InvestigationState(TypedDict):
    alert_id: str
    entity_id: str
    step_budget: int
    visited_tools: List[str]
    evidence_items: List[Dict[str, Any]]
    signals: List[Dict[str, Any]]
    score: int
    tier: str
    findings: List[str]
    proposed_actions: List[Dict[str, Any]]
    dry_run_diff: Optional[Dict[str, Any]]
    approval_status: str  # "NOT_REQUIRED", "PENDING", "APPROVED"
    audit_events: List[Dict[str, Any]]
    policy_version: str
    autonomy_mode: str
    next_tool: Optional[str]
    tool_calls: int
    incident_id: Optional[str]
    narrative: str
    grounding: Dict[str, Any]
    progress: List[Dict[str, Any]]
    error: Optional[str]
    pause_for_approval: bool
    
