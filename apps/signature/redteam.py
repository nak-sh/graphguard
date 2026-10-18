"""Deterministic red-team scenario matrix.

Variants are represented as isolated fixture transforms. The evaluator callback
is the same pipeline used by the normal scenario harness, so misses remain
visible rather than being converted into a success claim.
"""

from __future__ import annotations

import os
import time
import uuid
from typing import Any, Callable, Mapping, Sequence


VARIANTS = (
    ("baseline", "Original planted ring", "none"),
    ("long_cycle", "Add intermediaries beyond max cycle length", "increase max_len"),
    ("parallel_subrings", "Split flow into parallel sub-rings", "raise result limit and merge evidence"),
    ("late_transfers", "Delay one transfer outside the time window", "increase cycle window"),
    ("rotating_devices", "Rotate the device at every hop", "increase path/infrastructure coverage"),
    ("decayed_amounts", "Decay amounts to defeat pass-through tolerance", "adjust tolerance carefully"),
)


def _scratch_fixture(variant_id: str, graph_name: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]], str, str]:
    base_ts = 1_704_067_200
    if variant_id == "long_cycle":
        ids = [f"R-{i}" for i in range(1, 9)]
    elif variant_id == "parallel_subrings":
        ids = [f"R-{i}" for i in range(1, 7)]
    else:
        ids = [f"R-{i}" for i in range(1, 6)]
    accounts = [{"id": account_id, "status": "ACTIVE", "monthly_volume": 10000, "legit_activity_ratio": 0.1, "scenario": variant_id} for account_id in ids]
    transfers: list[dict[str, Any]] = []
    if variant_id == "parallel_subrings":
        rings = ([ids[0], ids[1]], [ids[0], ids[2]], [ids[0], ids[3]])
        for ring_index, ring in enumerate(rings):
            transfers.extend({"id": f"{variant_id}-{ring_index}-{idx}", "source": source, "target": target, "amount": 1000, "ts": base_ts + idx * 600, "scenario": variant_id} for idx, (source, target) in enumerate(zip(ring, ring[::-1])))
    else:
        for index, (source, target) in enumerate(zip(ids, ids[1:] + ids[:1])):
            timestamp = base_ts + index * 600
            if variant_id == "late_transfers" and index == len(ids) - 1:
                timestamp += 200000
            amount = 1000 * (0.25 ** index) if variant_id == "decayed_amounts" else 1000
            transfers.append({"id": f"{variant_id}-{index}", "source": source, "target": target, "amount": amount, "ts": timestamp, "scenario": variant_id})
    return accounts, transfers, ids[0], f"ALERT-{variant_id}-{graph_name[-6:]}"


def _run_scratch_variant(variant_id: str) -> dict[str, Any]:
    from falkordb import FalkorDB
    from apps.agent.workflow import InvestigationWorkflow
    from apps.graph_tools.tools import GraphTools

    graph_name = f"gg_redteam_{variant_id}_{uuid.uuid4().hex[:8]}"
    db = FalkorDB(host=os.getenv("GRAPHGUARD_DB_HOST", "localhost"), port=int(os.getenv("GRAPHGUARD_DB_PORT", "6379")))
    graph = db.select_graph(graph_name)
    accounts, transfers, entity_id, alert_id = _scratch_fixture(variant_id, graph_name)
    try:
        graph.query("UNWIND $rows AS row MERGE (a:Account {id: row.id}) SET a += row", {"rows": accounts})
        graph.query("MERGE (alert:Alert {id: $id}) SET alert.status='OPEN', alert.priority='HIGH'", {"id": alert_id})
        graph.query("MATCH (alert:Alert {id: $alert_id}), (a:Account {id: $entity_id}) MERGE (alert)-[:ABOUT]->(a)", {"alert_id": alert_id, "entity_id": entity_id})
        graph.query("UNWIND $rows AS row MATCH (source:Account {id: row.source}), (target:Account {id: row.target}) MERGE (source)-[r:SENT_MONEY {id: row.id}]->(target) SET r.amount=row.amount, r.ts=row.ts, r.scenario=row.scenario", {"rows": transfers})
        if variant_id == "baseline":
            graph.query("MERGE (d:Device {id: 'R-DEVICE'})")
            graph.query("MATCH (a:Account), (d:Device {id: 'R-DEVICE'}) WHERE a.scenario=$scenario MERGE (a)-[:USES_DEVICE]->(d)", {"scenario": variant_id})
        workflow = InvestigationWorkflow(tools=GraphTools(graph_name=graph_name))
        state = workflow.run(alert_id, entity_id)
        return {"caught": state.get("tier") != "NO_ACTION", "tier": state.get("tier"), "score": state.get("score"), "signals": [signal.get("rule") for signal in state.get("signals", [])], "scratch_graph": graph_name, "executed": True}
    finally:
        try:
            graph.delete()
        except Exception:
            pass


def red_team_matrix(evaluator: Callable[[Mapping[str, Any]], Mapping[str, Any]] | None = None) -> dict[str, Any]:
    rows = []
    for variant_id, description, suggested_knob in VARIANTS:
        payload = {"variant_id": variant_id, "description": description}
        if evaluator:
            result = dict(evaluator(payload))
        else:
            try:
                result = _run_scratch_variant(variant_id)
            except Exception as exc:
                result = {"caught": False, "signals": [], "executed": False, "error": str(exc)}
        rows.append({"variant_id": variant_id, "description": description, "suggested_policy_knob": suggested_knob, **result})
    return {"isolated_scratch_graphs": all(row.get("executed", False) for row in rows), "variants": rows, "honest_misses": [row["variant_id"] for row in rows if not row.get("caught", False)], "execution_status": "complete" if all(row.get("executed", False) for row in rows) else "partial_or_blocked"}
