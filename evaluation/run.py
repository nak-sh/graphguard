"""Run the reproducible T1-T3/D1-D4 evaluation harness."""

from __future__ import annotations

import json
import socket
from pathlib import Path
from typing import Any

from apps.actions.contracts import rollback_state_decision
from apps.agent.grounding import check_grounding
from apps.agent.workflow import InvestigationWorkflow
from apps.mock import action_lifecycle_check


ROOT = Path(__file__).resolve().parents[1]
GROUND_TRUTH = ROOT / "data" / "ground_truth.json"
ARTIFACT_DIR = ROOT / "artifacts"


def falkordb_available() -> bool:
    sock = socket.socket()
    sock.settimeout(0.5)
    try:
        return sock.connect_ex(("127.0.0.1", 6379)) == 0
    finally:
        sock.close()


def _ids_from_evidence(evidence: list[dict[str, Any]]) -> set[str]:
    found: set[str] = set()

    def visit(value: Any) -> None:
        if isinstance(value, dict):
            for key, child in value.items():
                if key.endswith("_id") or key in {"id", "cycle_nodes", "path_nodes", "connected_accounts"}:
                    if isinstance(child, str):
                        found.add(child)
                    elif isinstance(child, (list, tuple)):
                        found.update(str(item) for item in child)
                visit(child)
        elif isinstance(value, list):
            for child in value:
                visit(child)

    visit(evidence)
    return found


def evaluate() -> dict[str, Any]:
    ground_truth = json.loads(GROUND_TRUTH.read_text(encoding="utf-8"))
    report: dict[str, Any] = {
        "schema_version": 1,
        "source": "data/ground_truth.json",
        "database_available": falkordb_available(),
        "scenarios": [],
        "summary": {},
        "action_lifecycle": action_lifecycle_check(),
    }
    if not report["database_available"]:
        report["summary"] = {"status": "blocked", "reason": "FalkorDB is required for the real workflow"}
        return report

    workflow = InvestigationWorkflow()
    for scenario_id in ("T1", "T2", "T3", "D1", "D2", "D3", "D4"):
        scenario = ground_truth["scenarios"][scenario_id]
        alert_id = scenario["alert_ids"][0]
        entity_id = scenario["anchor"]
        state = workflow.run(alert_id, entity_id)
        evidence = state.get("evidence_items", [])
        grounding = check_grounding(state.get("narrative", ""), evidence)
        expected = scenario["expected"]["expected_disposition"]
        actual = state.get("tier", "UNKNOWN")
        escalated = actual != "NO_ACTION"
        scenario_report = {
            "scenario": scenario_id,
            "entity_id": entity_id,
            "expected_disposition": expected,
            "actual_disposition": actual,
            "disposition_match": expected == actual,
            "score": state.get("score", 0),
            "signal_rules": [signal.get("rule") for signal in state.get("signals", [])],
            "evidence_count": len(evidence),
            "evidence_traceable": all(item.get("id") and item.get("query_name") and item.get("data") is not None for item in evidence),
            "referenced_ids_count": len(_ids_from_evidence(evidence)),
            "grounding": {"grounded": grounding.grounded, "violations": list(grounding.violations)},
            "false_escalation": scenario_id.startswith("D") and escalated,
            "incident_id": state.get("incident_id"),
        }
        report["scenarios"].append(scenario_report)
    decoys = [row for row in report["scenarios"] if row["scenario"].startswith("D")]
    report["summary"] = {
        "status": "complete",
        "scenario_count": len(report["scenarios"]),
        "positive_matches": sum(row["disposition_match"] for row in report["scenarios"] if row["scenario"].startswith("T")),
        "false_escalations": sum(row["false_escalation"] for row in decoys),
        "grounding_violations": sum(len(row["grounding"]["violations"]) for row in report["scenarios"]),
        "all_evidence_traceable": all(row["evidence_traceable"] for row in report["scenarios"]),
        "zero_decoy_escalations": all(not row["false_escalation"] for row in decoys),
        "action_idempotency": report["action_lifecycle"]["idempotency"],
        "rollback_fidelity": report["action_lifecycle"]["rollback_fidelity"],
    }
    return report


def main() -> int:
    report = evaluate()
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    destination = ARTIFACT_DIR / "eval.json"
    destination.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["summary"].get("status") == "complete" and report["summary"].get("zero_decoy_escalations") else 2


if __name__ == "__main__":
    raise SystemExit(main())
