import uuid
from typing import Dict, Any
from langgraph.graph import StateGraph, END
from apps.graph_tools.tools import GraphTools
from apps.policy.scorer import score_investigation
from apps.agent.state import InvestigationState

class InvestigationWorkflow:
    def __init__(self, host: str = "localhost", port: int = 6379):
        self.tools = GraphTools(host=host, port=port)
        self.graph = self._build_graph()

    def _investigate_node(self, state: InvestigationState) -> Dict[str, Any]:
        entity_id = state["entity_id"]
        evidence = []
        visited = list(state.get("visited_tools", []))

        # 1. Inspect shared hardware
        infra = self.tools.find_shared_infrastructure(entity_id)
        visited.append("find_shared_infrastructure")
        for item in infra:
            evidence.append({
                "kind": "SHARED_INFRA",
                "infrastructure_id": item.infrastructure_id,
                "connected_accounts": item.connected_accounts,
                "is_hub": item.is_hub
            })

        # 2. Trace circular transactions
        cycles = self.tools.detect_transfer_cycles(entity_id)
        visited.append("detect_transfer_cycles")
        for c in cycles:
            evidence.append({
                "kind": "CYCLE",
                "cycle_nodes": c.cycle_nodes,
                "amounts": c.amounts,
                "timestamps": c.timestamps,
                "is_time_ordered": c.is_time_ordered
            })

        return {
            "visited_tools": visited,
            "evidence_items": evidence
        }

    def _score_node(self, state: InvestigationState) -> Dict[str, Any]:
        entity_id = state["entity_id"]
        infra = self.tools.find_shared_infrastructure(entity_id)
        cycles = self.tools.detect_transfer_cycles(entity_id)

        scoring_result = score_investigation(entity_id, infra, cycles)

        findings = []
        for signal in scoring_result.signals:
            findings.append(f"[{signal['rule']}] {signal['description']}")

        return {
            "score": scoring_result.score,
            "tier": scoring_result.tier,
            "signals": scoring_result.signals,
            "findings": findings
        }

    def _planner_node(self, state: InvestigationState) -> Dict[str, Any]:
        tier = state["tier"]
        entity_id = state["entity_id"]
        actions = []
        diff = None
        approval_status = "NOT_REQUIRED"

        if tier in ("AUTO_HOLD", "MANUAL_REVIEW"):
            action_type = "APPLY_HOLD" if tier == "AUTO_HOLD" else "FLAG_FOR_REVIEW"
            target_status = "HOLD" if tier == "AUTO_HOLD" else "UNDER_REVIEW"

            actions.append({
                "action_id": f"ACT-{uuid.uuid4().hex[:6]}",
                "type": action_type,
                "target_entity": entity_id,
                "tier": tier
            })

            # Dry-run diff: maps previous properties to proposed properties
            diff = {
                "entity_id": entity_id,
                "node_label": "Account",
                "previous_state": {"status": "ACTIVE"},
                "proposed_state": {"status": target_status},
                "policy_tier": tier
            }

            approval_status = "PENDING" if tier == "MANUAL_REVIEW" else "NOT_REQUIRED"

        return {
            "proposed_actions": actions,
            "dry_run_diff": diff,
            "approval_status": approval_status
        }

    def _build_graph(self):
        builder = StateGraph(InvestigationState)

        builder.add_node("investigate", self._investigate_node)
        builder.add_node("score", self._score_node)
        builder.add_node("plan", self._planner_node)

        builder.set_entry_point("investigate")
        builder.add_edge("investigate", "score")
        builder.add_edge("score", "plan")
        builder.add_edge("plan", END)

        return builder.compile()

    def run(self, alert_id: str, entity_id: str) -> InvestigationState:
        initial_state: InvestigationState = {
            "alert_id": alert_id,
            "entity_id": entity_id,
            "step_budget": 8,
            "visited_tools": [],
            "evidence_items": [],
            "signals": [],
            "score": 0,
            "tier": "NO_ACTION",
            "findings": [],
            "proposed_actions": [],
            "dry_run_diff": None,
            "approval_status": "NOT_REQUIRED",
            "audit_events": []
        }
        return self.graph.invoke(initial_state)