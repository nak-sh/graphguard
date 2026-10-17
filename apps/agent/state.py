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
    