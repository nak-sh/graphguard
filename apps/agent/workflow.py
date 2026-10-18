"""LangGraph investigation workflow with a deterministic offline playbook."""

from __future__ import annotations

import json
import time
import uuid
from typing import Any, Callable, Dict, Iterable, Mapping, Optional

from apps.actions.contracts import real_state_diff, StateSnapshot
from apps.agent.grounding import check_grounding
from apps.agent.providers import READ_ONLY_TOOLS, ToolSelector, deterministic_narrative
from apps.agent.state import InvestigationState
from apps.graph_tools.models import EvidenceBundle, EvidenceItem
from apps.graph_tools.tools import GraphTools
from apps.policy.scorer import explain_non_escalation, score_evidence

try:
    from langgraph.graph import END, StateGraph
    from langgraph.checkpoint.memory import MemorySaver
    from langgraph.types import Command, interrupt
except ImportError:  # pragma: no cover - offline pure imports remain available
    END = None
    StateGraph = None
    MemorySaver = None
    interrupt = None
    Command = None


class InvestigationWorkflow:
    """A stateful graph workflow whose facts always come from FalkorDB."""

    def __init__(
        self,
        host: str = "localhost",
        port: int = 6379,
        graph_name: str = "graphguard",
        *,
        tools: Optional[GraphTools] = None,
        selector: Optional[ToolSelector] = None,
        step_budget: int = 8,
    ) -> None:
        self.tools = tools or GraphTools(host=host, port=port, graph_name=graph_name)
        self.selector = selector or ToolSelector()
        self.step_budget = step_budget
        self._events: list[dict[str, Any]] = []
        self.checkpointer = MemorySaver() if MemorySaver is not None else None
        self.graph = self._build_graph() if StateGraph is not None else None

    def _emit(self, state: InvestigationState, event: str, **data: Any) -> None:
        payload = {"event": event, "ts": time.time(), **data}
        self._events.append(payload)
        state.setdefault("progress", []).append(payload)

    def _initialize_node(self, state: InvestigationState) -> Dict[str, Any]:
        alert = self.tools.get_alert(state["alert_id"])
        if alert is None:
            raise ValueError(f"alert not found: {state['alert_id']}")
        if str(alert.get("entity_id")) != state["entity_id"]:
            raise ValueError("alert is not linked to the requested entity")
        self._emit(state, "investigation_started", entity_id=state["entity_id"], alert_id=state["alert_id"])
        return {"error": None, "policy_version": state.get("policy_version", "2026-10-v1")}

    def _select_tool_node(self, state: InvestigationState) -> Dict[str, Any]:
        if state.get("tool_calls", 0) >= state["step_budget"]:
            return {"next_tool": None}
        choice = self.selector.choose(
            entity_id=state["entity_id"],
            evidence=state.get("evidence_items", []),
            visited=state.get("visited_tools", []),
            remaining_steps=state["step_budget"] - state.get("tool_calls", 0),
        )
        if choice.name not in READ_ONLY_TOOLS or choice.name in state.get("visited_tools", []):
            return {"next_tool": None}
        self._emit(state, "tool_selected", tool=choice.name, reason=choice.reason)
        return {"next_tool": choice.name}

    @staticmethod
    def _summary(kind: str, value: Any) -> str:
        if isinstance(value, Mapping):
            return f"{kind}: {json.dumps(dict(value), sort_keys=True, default=str)[:400]}"
        if isinstance(value, list):
            return f"{kind}: {len(value)} result(s)"
        return f"{kind}: {value}"

    def _evidence_item(self, state: InvestigationState, kind: str, query_name: str, data: Any, index: int = 0) -> dict[str, Any]:
        if hasattr(data, "model_dump"):
            raw = data.model_dump()
        elif isinstance(data, Mapping):
            raw = dict(data)
        else:
            raw = {"value": data}
        key = json.dumps(raw, sort_keys=True, default=str)
        evidence_id = self.tools._generate_evidence_id(query_name, f"{state['entity_id']}:{index}:{key}")
        return EvidenceItem(
            id=evidence_id,
            kind=kind,
            query_name=query_name,
            summary=self._summary(kind, raw),
            data=raw,
            flagged=kind in {"CYCLE", "MONEY_PATH", "SHARED_INFRA"},
            result_hash=__import__("hashlib").sha256(key.encode()).hexdigest(),
        ).model_dump()

    def _run_tool_node(self, state: InvestigationState) -> Dict[str, Any]:
        name = state.get("next_tool")
        if not name:
            return {}
        started = time.perf_counter()
        entity_id = state["entity_id"]
        if name == "get_entity_summary":
            raw_results: Iterable[Any] = [self.tools.get_entity_summary(entity_id)]
            kind = "ENTITY_SUMMARY"
        elif name == "get_neighborhood":
            raw_results = [self.tools.get_neighborhood(entity_id, max_hops=4, hub_cutoff=20, limit=200)]
            kind = "NEIGHBORHOOD"
        elif name == "find_shared_infrastructure_device":
            raw_results = self.tools.find_shared_devices(entity_id, hub_cutoff=20, limit=50)
            kind = "SHARED_INFRA"
        elif name == "find_shared_infrastructure_ip":
            raw_results = self.tools.find_shared_ips(entity_id, hub_cutoff=20, limit=50)
            kind = "SHARED_INFRA"
        elif name == "trace_money_paths":
            raw_results = self.tools.trace_money_paths(entity_id, max_hops=5, limit=100)
            kind = "MONEY_PATH"
        elif name == "detect_transfer_cycles":
            raw_results = self.tools.detect_transfer_cycles(entity_id, max_hops=6, limit=100)
            kind = "CYCLE"
        else:  # fail closed if a provider ever returns an unknown name
            return {"next_tool": None}
        evidence = list(state.get("evidence_items", []))
        new_items = [self._evidence_item(state, kind, name, item, index) for index, item in enumerate(raw_results)]
        if not new_items:
            new_items = [self._evidence_item(state, kind, name, {"result_count": 0}, 0)]
        evidence.extend(new_items)
        elapsed_ms = round((time.perf_counter() - started) * 1000, 2)
        self._emit(state, "tool_completed", tool=name, duration_ms=elapsed_ms, result_count=len(new_items))
        return {
            "evidence_items": evidence,
            "visited_tools": [*state.get("visited_tools", []), name],
            "tool_calls": state.get("tool_calls", 0) + 1,
            "next_tool": None,
        }

    def _score_node(self, state: InvestigationState) -> Dict[str, Any]:
        bundle = EvidenceBundle(
            entity_id=state["entity_id"],
            items=[EvidenceItem.model_validate(item) for item in state.get("evidence_items", [])],
            policy_version=state.get("policy_version", "2026-10-v1"),
        )
        result = score_evidence(state["entity_id"], bundle, policy_version=bundle.policy_version)
        findings = [f"[{signal['rule']}] {signal['description']}" for signal in result.signals]
        self._emit(state, "evidence_scored", score=result.score, tier=result.tier, signal_count=len(result.signals))
        return {"score": result.score, "tier": result.tier, "signals": result.signals, "findings": findings}

    @staticmethod
    def _affected_entities(state: InvestigationState) -> list[str]:
        ids = {state["entity_id"]}
        for item in state.get("evidence_items", []):
            data = item.get("data", {})
            for key in ("cycle_nodes", "path_nodes", "connected_accounts"):
                values = data.get(key, []) if isinstance(data, Mapping) else []
                if isinstance(values, (list, tuple)):
                    ids.update(str(value) for value in values if value)
        return sorted(ids)

    def _planner_node(self, state: InvestigationState) -> Dict[str, Any]:
        tier = state.get("tier", "NO_ACTION")
        if tier == "NO_ACTION":
            explanation = explain_non_escalation(
                state["entity_id"],
                [EvidenceItem.model_validate(item) for item in state.get("evidence_items", [])],
                state.get("policy_version", "2026-10-v1"),
            )
            narrative = deterministic_narrative(state["entity_id"], state.get("score", 0), tier, state.get("evidence_items", []), [explanation["explanation"]])
            grounding = check_grounding(narrative, state.get("evidence_items", []))
            self._emit(state, "no_action_explained", signals_checked=len(explanation["signals_checked"]))
            return {"proposed_actions": [], "dry_run_diff": None, "approval_status": "NOT_REQUIRED", "narrative": narrative, "grounding": grounding.__dict__}

        targets = self._affected_entities(state)
        action_type = "APPLY_HOLD" if tier == "AUTO_HOLD" else "FLAG_FOR_REVIEW"
        status = "HOLD" if tier == "AUTO_HOLD" else "UNDER_REVIEW"
        states = self.tools.get_account_states(targets)
        actions: list[dict[str, Any]] = []
        diffs: list[dict[str, Any]] = []
        for target in targets:
            action = {
                "action_id": f"ACT-{uuid.uuid4().hex[:10]}",
                "type": action_type,
                "target_entity": target,
                "tier": tier,
                "target_status": status,
            }
            actions.append(action)
            current = states.get(target, {"status": "UNKNOWN"})
            diffs.append(real_state_diff(StateSnapshot(target, current.get("status"), current), action_type, policy_tier=tier))
        pending = tier == "MANUAL_REVIEW" or len(actions) > 3 or any(states.get(target, {}).get("high_value") for target in targets)
        approval_status = "PENDING" if pending else "NOT_REQUIRED"
        narrative = deterministic_narrative(state["entity_id"], state.get("score", 0), tier, state.get("evidence_items", []), state.get("findings", []))
        grounding = check_grounding(narrative, state.get("evidence_items", []))
        self._emit(state, "action_plan_ready", action_count=len(actions), approval_status=approval_status)
        aggregate_diff = {
            "actions": diffs,
            "policy_tier": tier,
            "writes": False,
        }
        if diffs:
            # Keep the v1 single-target shape as a compatibility view while
            # exposing the complete affected-account diff in ``actions``.
            aggregate_diff.update({key: diffs[0][key] for key in ("entity_id", "node_label", "previous_state", "proposed_state", "changes")})
        return {
            "proposed_actions": actions,
            "dry_run_diff": aggregate_diff,
            "approval_status": approval_status,
            "narrative": narrative,
            "grounding": grounding.__dict__,
        }

    def _persist_node(self, state: InvestigationState) -> Dict[str, Any]:
        incident_id = state.get("incident_id") or f"INC-{uuid.uuid4().hex[:12]}"
        referenced = self._affected_entities(state)
        incident = {
            "id": incident_id,
            "alert_id": state["alert_id"],
            "entity_id": state["entity_id"],
            "created_at": int(time.time()),
            "status": "OPEN",
            "summary": state.get("narrative", ""),
            "policy_version": state.get("policy_version", "2026-10-v1"),
            "score": state.get("score", 0),
            "tier": state.get("tier", "NO_ACTION"),
            "approval_status": state.get("approval_status", "NOT_REQUIRED"),
            "proposed_actions": state.get("proposed_actions", []),
            "dry_run_diff": state.get("dry_run_diff") or {},
        }
        self.tools.create_incident(incident, state.get("evidence_items", []), referenced)
        self._emit(state, "incident_persisted", incident_id=incident_id)
        return {"incident_id": incident_id}

    def _approval_gate_node(self, state: InvestigationState) -> Dict[str, Any]:
        if state.get("pause_for_approval") and state.get("approval_status") == "PENDING" and interrupt is not None:
            decision = interrupt({"incident_id": state.get("incident_id"), "message": "Human approval required"})
            approved = bool(decision.get("approved")) if isinstance(decision, Mapping) else bool(decision)
            if state.get("incident_id"):
                self.tools.update_incident(state["incident_id"], {"approval_status": "APPROVED" if approved else "REJECTED", "approved_by": "interrupt"})
            return {"approval_status": "APPROVED" if approved else "REJECTED"}
        return {}

    def _route_after_select(self, state: InvestigationState) -> str:
        return "run_tool" if state.get("next_tool") else "score"

    def _build_graph(self) -> Any:
        builder = StateGraph(InvestigationState)
        builder.add_node("initialize", self._initialize_node)
        builder.add_node("select_tool", self._select_tool_node)
        builder.add_node("run_tool", self._run_tool_node)
        builder.add_node("score", self._score_node)
        builder.add_node("plan", self._planner_node)
        builder.add_node("persist", self._persist_node)
        builder.add_node("approval_gate", self._approval_gate_node)
        builder.set_entry_point("initialize")
        builder.add_edge("initialize", "select_tool")
        builder.add_conditional_edges("select_tool", self._route_after_select, {"run_tool": "run_tool", "score": "score"})
        builder.add_edge("run_tool", "select_tool")
        builder.add_edge("score", "plan")
        builder.add_edge("plan", "persist")
        builder.add_edge("persist", "approval_gate")
        builder.add_edge("approval_gate", END)
        if self.checkpointer is not None:
            return builder.compile(checkpointer=self.checkpointer)
        return builder.compile()

    def _initial_state(self, alert_id: str, entity_id: str, *, pause_for_approval: bool = False, autonomy_mode: str = "APPROVE") -> InvestigationState:
        return {
            "alert_id": alert_id,
            "entity_id": entity_id,
            "step_budget": self.step_budget,
            "visited_tools": [],
            "evidence_items": [],
            "signals": [],
            "score": 0,
            "tier": "NO_ACTION",
            "findings": [],
            "proposed_actions": [],
            "dry_run_diff": None,
            "approval_status": "NOT_REQUIRED",
            "audit_events": [],
            "policy_version": "2026-10-v1",
            "autonomy_mode": autonomy_mode,
            "next_tool": None,
            "tool_calls": 0,
            "incident_id": None,
            "narrative": "",
            "grounding": {},
            "progress": [],
            "error": None,
            "pause_for_approval": pause_for_approval,
        }

    def run(self, alert_id: str, entity_id: str, *, pause_for_approval: bool = False, autonomy_mode: str = "APPROVE", thread_id: Optional[str] = None) -> InvestigationState:
        self._events = []
        state = self._initial_state(alert_id, entity_id, pause_for_approval=pause_for_approval, autonomy_mode=autonomy_mode)
        if self.graph is None:
            for node in (self._initialize_node, self._select_tool_node, self._run_tool_node):
                update = node(state)
                state.update(update)
                while node is self._run_tool_node and state.get("next_tool"):
                    update = self._select_tool_node(state)
                    state.update(update)
                    if not state.get("next_tool"):
                        break
                    state.update(self._run_tool_node(state))
            state.update(self._score_node(state))
            state.update(self._planner_node(state))
            state.update(self._persist_node(state))
            return state
        config = {"configurable": {"thread_id": thread_id or f"thread-{uuid.uuid4().hex}"}}
        return self.graph.invoke(state, config=config)

    def events(self) -> list[dict[str, Any]]:
        return list(self._events)

    def resume_approval(self, thread_id: str, approved: bool) -> InvestigationState:
        if self.graph is None or Command is None:
            raise RuntimeError("LangGraph checkpointing is unavailable")
        return self.graph.invoke(Command(resume={"approved": approved}), config={"configurable": {"thread_id": thread_id}})

    def stream(self, alert_id: str, entity_id: str, **kwargs: Any) -> Iterable[dict[str, Any]]:
        result = self.run(alert_id, entity_id, **kwargs)
        yield from result.get("progress", [])
        yield {"event": "investigation_complete", "incident_id": result.get("incident_id"), "state": result}
