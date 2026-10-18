"""Bounded, parameterised FalkorDB graph tools.

Only this module talks to FalkorDB.  The temporal predicates are also exposed as
pure functions so policy and unit tests never need a running database.
"""

from __future__ import annotations

import hashlib
import json
import re
import time
from typing import Any, Iterable, List, Mapping, Optional, Sequence, Tuple

try:  # Keep pure contracts/tests importable when the optional DB client is absent.
    from falkordb import FalkorDB
except ImportError:  # pragma: no cover - exercised in dependency-free environments
    FalkorDB = None  # type: ignore[assignment,misc]

from apps.graph_tools.models import (
    CycleResult,
    EdgeSummary,
    EntitySummaryResult,
    MoneyPathResult,
    NeighborhoodResult,
    NodeSummary,
    SharedInfraResult,
    SubgraphResult,
)


MAX_HOPS = 6
MAX_NEIGHBORHOOD_HOPS = 4
MAX_RESULTS = 1000
MAX_WINDOW_SECONDS = 31_536_000
DEFAULT_CYCLE_WINDOW_SECONDS = 86_400
_ALLOWED_RELATIONSHIPS = ("USES_DEVICE", "USED_IP", "SENT_MONEY")
_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$")


def _bounded_int(name: str, value: int, low: int, high: int) -> int:
    # bool is an int subclass but is never a valid query bound.
    if isinstance(value, bool) or not isinstance(value, int) or not low <= value <= high:
        raise ValueError(f"{name} must be an integer between {low} and {high}")
    return value


def _entity_id(value: str) -> str:
    if not isinstance(value, str) or not _ID_RE.fullmatch(value):
        raise ValueError("entity identifiers must be 1-128 safe identifier characters")
    return value


def _numeric(value: Any, *, integer: bool = False) -> Optional[int | float]:
    if isinstance(value, bool):
        return None
    try:
        return int(value) if integer else float(value)
    except (TypeError, ValueError):
        return None


def _cycle_window(timestamps: Sequence[int | float]) -> float:
    return max(timestamps) - min(timestamps) if timestamps else 0


def is_time_respecting_cycle(timestamps: Sequence[int | float], max_window_seconds: int) -> bool:
    """Return whether a directed cycle is time respecting, independent of rotation.

    A circular sequence may have one timestamp descent: that descent is the
    wrap from the end of a chronological cycle back to its first transfer.  A
    reverse-unrolled path has multiple descents and is rejected.  We inspect
    the circular sequence as returned by FalkorDB and never reverse its nodes
    or edges.
    """

    if not isinstance(max_window_seconds, int) or isinstance(max_window_seconds, bool):
        return False
    if max_window_seconds < 0 or len(timestamps) < 3:
        return False
    values: list[float] = []
    for value in timestamps:
        number = _numeric(value)
        if number is None:
            return False
        values.append(number)
    if _cycle_window(values) > max_window_seconds:
        return False
    descents = sum(1 for left, right in zip(values, values[1:] + values[:1]) if left > right)
    return descents <= 1


def max_minus_min_within_window(timestamps: Sequence[int | float], max_window_seconds: int) -> bool:
    """Pure max-minus-min window predicate shared by path and cycle checks."""

    if not isinstance(max_window_seconds, int) or isinstance(max_window_seconds, bool) or max_window_seconds < 0:
        return False
    values = [_numeric(value) for value in timestamps]
    return bool(values) and all(value is not None for value in values) and _cycle_window(values) <= max_window_seconds


def cycle_is_time_ordered(timestamps: Sequence[int | float], max_window_seconds: int) -> bool:
    """Readable alias used by callers and tests."""

    return is_time_respecting_cycle(timestamps, max_window_seconds)


def is_cycle_time_ordered(timestamps: Sequence[int | float], max_window_seconds: int) -> bool:
    return is_time_respecting_cycle(timestamps, max_window_seconds)


def is_time_respecting_path(timestamps: Sequence[int | float], max_window_seconds: int) -> bool:
    """Check a non-circular directed path in chronological order."""

    if not isinstance(max_window_seconds, int) or isinstance(max_window_seconds, bool):
        return False
    if max_window_seconds < 0 or not timestamps:
        return False
    values: list[float] = []
    for value in timestamps:
        number = _numeric(value)
        if number is None:
            return False
        values.append(number)
    return all(left <= right for left, right in zip(values, values[1:])) and _cycle_window(values) <= max_window_seconds


def _obj_properties(obj: Any) -> dict[str, Any]:
    if obj is None:
        return {}
    props = getattr(obj, "properties", None)
    if props is None and isinstance(obj, dict):
        props = obj.get("properties", obj)
    return dict(props or {})


def _obj_id(obj: Any) -> Optional[str]:
    if obj is None:
        return None
    if isinstance(obj, str):
        return obj
    props = _obj_properties(obj)
    value = props.get("id")
    return str(value) if value is not None else None


def _obj_label(obj: Any) -> str:
    if obj is None:
        return "Unknown"
    labels = getattr(obj, "labels", None)
    if labels:
        return str(next(iter(labels)))
    if isinstance(obj, dict):
        label = obj.get("label") or obj.get("labels")
        if isinstance(label, (list, tuple)):
            return str(label[0]) if label else "Unknown"
        if label:
            return str(label)
    return str(getattr(obj, "label", "Unknown"))


def _path_nodes(path: Any) -> list[Any]:
    return list(getattr(path, "nodes", []) or [])


def _path_relationships(path: Any) -> list[Any]:
    return list(getattr(path, "relationships", []) or [])


def _relationship_property(rel: Any, key: str, default: Any = None) -> Any:
    props = _obj_properties(rel)
    if key in props:
        return props[key]
    return getattr(rel, key, default)


def _relationship_endpoints(rel: Any) -> tuple[Optional[str], Optional[str]]:
    src = getattr(rel, "src_node", None)
    dst = getattr(rel, "dest_node", None)
    if src is None:
        src = getattr(rel, "source", None)
    if dst is None:
        dst = getattr(rel, "target", None)
    return _obj_id(src), _obj_id(dst)


def _relationship_name(rel: Any) -> str:
    value = getattr(rel, "relation", None) or getattr(rel, "type", None) or getattr(rel, "relationship", None)
    return str(value or "UNKNOWN")


class GraphTools:
    """The sole FalkorDB boundary for read-only graph analysis."""

    def __init__(self, host: str = "localhost", port: int = 6379, graph_name: str = "graphguard"):
        if FalkorDB is None:
            raise RuntimeError("FalkorDB client is unavailable; graph integration was not faked")
        self.db = FalkorDB(host=host, port=port)
        self.g = self.db.select_graph(graph_name)

    def _generate_evidence_id(self, query_name: str, key: str) -> str:
        return f"EV-{query_name[:3].upper()}-{hashlib.sha256(key.encode()).hexdigest()[:12]}"

    def _query(self, query: str, params: dict[str, Any]) -> Any:
        """Single chokepoint for FalkorDB calls; no other code owns a DB client."""

        return self.g.query(query, params)

    def get_alerts(self, status: Optional[str] = None, limit: int = 100) -> list[dict[str, Any]]:
        """Return alert queue rows from FalkorDB, never from a hard-coded UI list."""

        limit = _bounded_int("limit", limit, 1, MAX_RESULTS)
        query = """
        MATCH (alert:Alert)-[:ABOUT]->(account:Account)
        WHERE ($status IS NULL OR alert.status = $status)
        RETURN properties(alert) AS alert, account.id AS entity_id
        ORDER BY alert.priority, alert.created_at, alert.id
        LIMIT $limit
        """
        result = self._query(query, {"status": status, "limit": limit})
        rows: list[dict[str, Any]] = []
        for row in getattr(result, "result_set", []) or []:
            if len(row) < 2:
                continue
            alert = dict(row[0] or {})
            alert["entity_id"] = str(row[1])
            rows.append(alert)
        return rows

    def get_alert(self, alert_id: str) -> Optional[dict[str, Any]]:
        alert_id = _entity_id(alert_id)
        query = """
        MATCH (alert:Alert {id: $alert_id})-[:ABOUT]->(account:Account)
        RETURN properties(alert) AS alert, account.id AS entity_id
        LIMIT 1
        """
        result = self._query(query, {"alert_id": alert_id})
        rows = getattr(result, "result_set", []) or []
        if not rows:
            return None
        alert = dict(rows[0][0] or {})
        alert["entity_id"] = str(rows[0][1])
        return alert

    def get_account_states(self, entity_ids: Sequence[str]) -> dict[str, dict[str, Any]]:
        ids = [_entity_id(entity_id) for entity_id in entity_ids]
        if not ids:
            return {}
        result = self._query(
            "MATCH (a:Account) WHERE a.id IN $entity_ids RETURN a.id, properties(a)",
            {"entity_ids": ids},
        )
        states: dict[str, dict[str, Any]] = {}
        for row in getattr(result, "result_set", []) or []:
            if len(row) >= 2:
                states[str(row[0])] = dict(row[1] or {})
        return states

    def create_incident(
        self,
        incident: Mapping[str, Any],
        evidence_items: Sequence[Mapping[str, Any]],
        referenced_ids: Sequence[str],
    ) -> dict[str, Any]:
        """Persist incident/evidence/provenance nodes in FalkorDB."""

        incident_row = dict(incident)
        incident_id = _entity_id(str(incident_row["id"]))
        incident_row["id"] = incident_id
        incident_row["created_at"] = incident_row.get("created_at", int(time.time()))
        incident_row["proposed_actions_json"] = json.dumps(
            incident_row.get("proposed_actions", []), sort_keys=True, default=str
        )
        incident_row.pop("proposed_actions", None)
        incident_row["dry_run_diff_json"] = json.dumps(
            incident_row.get("dry_run_diff", {}), sort_keys=True, default=str
        )
        incident_row.pop("dry_run_diff", None)
        incident_row["evidence_ids_json"] = json.dumps(
            [str(item.get("id")) for item in evidence_items], sort_keys=True
        )
        query = """
        MERGE (incident:Incident {id: $id})
        SET incident += $incident
        WITH incident
        OPTIONAL MATCH (alert:Alert {id: $alert_id})
        FOREACH (_ IN CASE WHEN alert IS NULL THEN [] ELSE [1] END |
          MERGE (incident)-[:ABOUT]->(alert))
        RETURN properties(incident)
        """
        params = {"id": incident_id, "incident": incident_row, "alert_id": incident_row.get("alert_id")}
        result = self._query(query, params)

        refs = [_entity_id(str(value)) for value in referenced_ids if value]
        for item in evidence_items:
            evidence = dict(item)
            evidence_id = _entity_id(str(evidence["id"]))
            evidence["id"] = evidence_id
            evidence["created_at"] = evidence.get("created_at", int(time.time()))
            evidence["data_json"] = json.dumps(evidence.get("data", {}), sort_keys=True, default=str)
            evidence.pop("data", None)
            evidence_query = """
            MERGE (ev:Evidence {id: $id})
            SET ev += $evidence
            WITH ev
            MATCH (incident:Incident {id: $incident_id})
            MERGE (incident)-[:SUPPORTED_BY]->(ev)
            WITH ev
            UNWIND $refs AS ref_id
            MATCH (referenced {id: ref_id})
            MERGE (ev)-[:REFERENCES]->(referenced)
            """
            self._query(evidence_query, {"id": evidence_id, "evidence": evidence, "incident_id": incident_id, "refs": refs})
        return {"id": incident_id, "properties": incident_row, "evidence_count": len(evidence_items)}

    def get_incident(self, incident_id: str) -> Optional[dict[str, Any]]:
        incident_id = _entity_id(incident_id)
        result = self._query(
            "MATCH (incident:Incident {id: $incident_id}) RETURN properties(incident) LIMIT 1",
            {"incident_id": incident_id},
        )
        rows = getattr(result, "result_set", []) or []
        if not rows:
            return None
        value = dict(rows[0][0] or {})
        for key in ("proposed_actions_json", "dry_run_diff_json", "evidence_ids_json"):
            if key in value:
                try:
                    value[key.removesuffix("_json")] = json.loads(value[key])
                except (TypeError, json.JSONDecodeError):
                    value[key.removesuffix("_json")] = [] if key.endswith("ids_json") else {}
        return value

    def update_incident(self, incident_id: str, updates: Mapping[str, Any]) -> Optional[dict[str, Any]]:
        incident_id = _entity_id(incident_id)
        result = self._query(
            "MATCH (incident:Incident {id: $incident_id}) SET incident += $updates RETURN properties(incident)",
            {"incident_id": incident_id, "updates": dict(updates)},
        )
        rows = getattr(result, "result_set", []) or []
        return dict(rows[0][0] or {}) if rows else None

    def list_incidents(self, limit: int = 100) -> list[dict[str, Any]]:
        limit = _bounded_int("limit", limit, 1, MAX_RESULTS)
        result = self._query(
            "MATCH (incident:Incident) RETURN properties(incident) ORDER BY incident.created_at DESC LIMIT $limit",
            {"limit": limit},
        )
        return [dict(row[0] or {}) for row in getattr(result, "result_set", []) or [] if row]

    def get_incident_evidence(self, incident_id: str) -> list[dict[str, Any]]:
        incident_id = _entity_id(incident_id)
        result = self._query(
            "MATCH (:Incident {id: $incident_id})-[:SUPPORTED_BY]->(ev:Evidence) RETURN properties(ev) ORDER BY ev.created_at, ev.id",
            {"incident_id": incident_id},
        )
        evidence: list[dict[str, Any]] = []
        for row in getattr(result, "result_set", []) or []:
            if not row:
                continue
            value = dict(row[0] or {})
            if "data_json" in value:
                try:
                    value["data"] = json.loads(value["data_json"])
                except (TypeError, json.JSONDecodeError):
                    value["data"] = {}
            evidence.append(value)
        return evidence

    def get_entity_summary(self, entity_id: str, limit: int = 50) -> EntitySummaryResult:
        entity_id = _entity_id(entity_id)
        limit = _bounded_int("limit", limit, 1, MAX_RESULTS)
        query = """
        MATCH (a:Account {id: $entity_id})
        OPTIONAL MATCH (a)-[r]-(n)
        WHERE type(r) IN $rel_allowlist
        RETURN a, n, r
        LIMIT $limit
        """
        result = self._query(query, {"entity_id": entity_id, "rel_allowlist": list(_ALLOWED_RELATIONSHIPS), "limit": limit})
        account = None
        neighbors: dict[str, NodeSummary] = {}
        for row in getattr(result, "result_set", []) or []:
            if not row:
                continue
            account = account or (row[0] if len(row) > 0 else None)
            node = row[1] if len(row) > 1 else None
            node_id = _obj_id(node)
            if node_id and node_id not in neighbors:
                neighbors[node_id] = NodeSummary(id=node_id, label=_obj_label(node), properties=_obj_properties(node))
        props = _obj_properties(account)
        return EntitySummaryResult(entity_id=entity_id, label=_obj_label(account) if account else "Account", properties=props, direct_neighbors=list(neighbors.values()))

    def get_neighborhood(
        self,
        entity_id: str,
        max_hops: int = 2,
        limit: int = 50,
        hub_cutoff: int = 20,
        rel_allowlist: Optional[Sequence[str]] = None,
    ) -> NeighborhoodResult:
        entity_id = _entity_id(entity_id)
        max_hops = _bounded_int("max_hops", max_hops, 1, MAX_NEIGHBORHOOD_HOPS)
        limit = _bounded_int("limit", limit, 1, MAX_RESULTS)
        hub_cutoff = _bounded_int("hub_cutoff", hub_cutoff, 2, MAX_RESULTS)
        rels = tuple(rel_allowlist or _ALLOWED_RELATIONSHIPS)
        if not rels or any(rel not in _ALLOWED_RELATIONSHIPS for rel in rels):
            raise ValueError("rel_allowlist contains an unsupported relationship")
        # The range is interpolated only after strict integer validation; entity
        # values, relationship values and result limits remain query parameters.
        query = f"""
        MATCH p = (a:Account {{id: $entity_id}})-[*1..{max_hops}]-(m)
        WHERE all(r IN relationships(p) WHERE type(r) IN $rel_allowlist)
          AND all(n IN nodes(p)[1..] WHERE coalesce(n.is_shared_hub, false) = false)
        RETURN [n IN nodes(p) | {{id: n.id, label: labels(n), properties: properties(n)}}] AS path_nodes,
               [r IN relationships(p) | {{source: startNode(r).id, target: endNode(r).id,
                 relationship: type(r), properties: properties(r)}}] AS path_edges
        LIMIT $limit
        """
        result = self._query(query, {"entity_id": entity_id, "rel_allowlist": list(rels), "limit": limit})
        nodes: dict[str, NodeSummary] = {}
        edges: dict[tuple[str, ...], EdgeSummary] = {}
        degree: dict[str, set[str]] = {}
        raw_paths = list(getattr(result, "result_set", []) or [])
        for row in raw_paths:
            if not row:
                continue
            path_nodes = row[0] or []
            for node in path_nodes:
                node_id = _obj_id(node)
                if node_id:
                    nodes.setdefault(node_id, NodeSummary(id=node_id, label=_obj_label(node), properties=_obj_properties(node)))
            path_edges = row[1] if len(row) > 1 else []
            for rel in path_edges or []:
                src = str(rel.get("source")) if rel.get("source") is not None else None
                dst = str(rel.get("target")) if rel.get("target") is not None else None
                name = str(rel.get("relationship", "UNKNOWN"))
                if not src or not dst or name not in rels:
                    continue
                rel_properties = dict(rel.get("properties") or {})
                # A relationship id identifies one transfer across repeated
                # path rows.  Without one, endpoint/type is the stable UI
                # identity and reverse traversal rows collapse together.
                relationship_id = rel_properties.get("id")
                key = (
                    str(relationship_id), name
                ) if relationship_id is not None else (min(src, dst), max(src, dst), name)
                edges.setdefault(key, EdgeSummary(source=src, target=dst, relationship=name, properties=rel_properties))
                degree.setdefault(src, set()).add(dst)
                degree.setdefault(dst, set()).add(src)
        hub_nodes = sorted(
            node_id
            for node_id, node in nodes.items()
            if node_id != entity_id and (bool(node.properties.get("is_shared_hub")) or len(degree.get(node_id, set())) >= hub_cutoff)
        )
        hub_set = set(hub_nodes)
        kept_nodes = [node for node_id, node in nodes.items() if node_id not in hub_set]
        kept_edges = [edge for edge in edges.values() if edge.source not in hub_set and edge.target not in hub_set]
        # A FalkorDB LIMIT applies to paths.  ``truncated`` tells the explorer
        # that deduplication may have reduced that row count further.
        return NeighborhoodResult(
            entity_id=entity_id,
            max_hops=max_hops,
            hub_cutoff=hub_cutoff,
            nodes=kept_nodes,
            edges=kept_edges,
            hub_nodes=hub_nodes,
            truncated=len(raw_paths) >= limit,
        )

    def find_shared_infrastructure(
        self,
        entity_id: str,
        hub_cutoff: int = 20,
        kind: str = "device",
        window_seconds: int = DEFAULT_CYCLE_WINDOW_SECONDS,
        min_accounts: int = 2,
        limit: int = 50,
        window: Optional[int] = None,
    ) -> List[SharedInfraResult]:
        # v1 used the second positional argument for hub_cutoff; accepting a
        # string there makes the v2 device/IP shorthand unambiguous without
        # changing existing callers.
        if isinstance(hub_cutoff, str):
            kind, hub_cutoff = hub_cutoff, 20
        if window is not None:
            window_seconds = window
        entity_id = _entity_id(entity_id)
        hub_cutoff = _bounded_int("hub_cutoff", hub_cutoff, 2, MAX_RESULTS)
        window_seconds = _bounded_int("window_seconds", window_seconds, 0, MAX_WINDOW_SECONDS)
        min_accounts = _bounded_int("min_accounts", min_accounts, 2, MAX_RESULTS)
        limit = _bounded_int("limit", limit, 1, MAX_RESULTS)
        kind_key = kind.lower().replace("address", "").replace("ip", "ip")
        if kind_key not in {"device", "ip"}:
            raise ValueError("kind must be 'device' or 'ip'")
        label, relationship, output_type = ("Device", "USES_DEVICE", "Device") if kind_key == "device" else ("IPAddress", "USED_IP", "IPAddress")
        query = f"""
        MATCH (a:Account {{id: $entity_id}})-[:{relationship}]->(infra:{label})<-[:{relationship}]-(other:Account)
        WHERE other.id <> a.id
        WITH infra, collect(DISTINCT other.id) AS others
        WITH infra, others, size(others) + 1 AS total_count
        WHERE total_count >= $min_accounts
        RETURN infra.id AS infrastructure_id,
               others AS connected_accounts,
               total_count AS total_count,
               coalesce(infra.is_shared_hub, false) AS explicit_hub
        LIMIT $limit
        """
        result = self._query(query, {"entity_id": entity_id, "min_accounts": min_accounts, "limit": limit, "window_seconds": window_seconds})
        output: list[SharedInfraResult] = []
        for row in getattr(result, "result_set", []) or []:
            if len(row) < 3:
                continue
            infrastructure_id = str(row[0])
            connected = list(dict.fromkeys(str(item) for item in (row[1] or []) if item is not None))
            total_count = int(row[2])
            explicit_hub = bool(row[3]) if len(row) > 3 else False
            output.append(
                SharedInfraResult(
                    entity_id=entity_id,
                    infrastructure_id=infrastructure_id,
                    infrastructure_type=output_type,
                    connected_accounts=connected,
                    is_hub=explicit_hub or total_count >= hub_cutoff,
                    hub_degree=total_count,
                    window_seconds=window_seconds,
                )
            )
        return output

    def analyze_shared_infrastructure(self, *args: Any, **kwargs: Any) -> List[SharedInfraResult]:
        return self.find_shared_infrastructure(*args, **kwargs)

    def find_shared_devices(self, entity_id: str, **kwargs: Any) -> List[SharedInfraResult]:
        kwargs["kind"] = "device"
        return self.find_shared_infrastructure(entity_id, **kwargs)

    def find_shared_ips(self, entity_id: str, **kwargs: Any) -> List[SharedInfraResult]:
        kwargs["kind"] = "ip"
        return self.find_shared_infrastructure(entity_id, **kwargs)

    def trace_money_paths(
        self,
        source_id: str,
        target_id: Optional[str] = None,
        max_hops: int = 4,
        window_seconds: int = DEFAULT_CYCLE_WINDOW_SECONDS,
        min_amount: float = 0.0,
        limit: int = 50,
        window: Optional[int] = None,
    ) -> List[MoneyPathResult]:
        if window is not None:
            window_seconds = window
        source_id = _entity_id(source_id)
        if target_id is not None:
            target_id = _entity_id(target_id)
        max_hops = _bounded_int("max_hops", max_hops, 1, MAX_HOPS)
        window_seconds = _bounded_int("window_seconds", window_seconds, 0, MAX_WINDOW_SECONDS)
        limit = _bounded_int("limit", limit, 1, MAX_RESULTS)
        if isinstance(min_amount, bool) or not isinstance(min_amount, (int, float)) or min_amount < 0:
            raise ValueError("min_amount must be a non-negative number")
        query = f"""
        MATCH p = (source:Account {{id: $source_id}})-[:SENT_MONEY*1..{max_hops}]->(target:Account)
        WHERE ($target_id IS NULL OR target.id = $target_id)
          AND all(r IN relationships(p) WHERE r.amount >= $min_amount)
        RETURN [n IN nodes(p) | n.id] AS path_nodes,
               [r IN relationships(p) | r.amount] AS amounts,
               [r IN relationships(p) | r.ts] AS timestamps,
               coalesce(target.confirmed_bad, false) AS target_confirmed_bad,
               [r IN relationships(p) | coalesce(r.transfer_kind, '')] AS transfer_kinds
        LIMIT $limit
        """
        result = self._query(query, {"source_id": source_id, "target_id": target_id, "min_amount": float(min_amount), "window_seconds": window_seconds, "limit": limit})
        paths: list[MoneyPathResult] = []
        for row in getattr(result, "result_set", []) or []:
            if not row or len(row) < 3:
                continue
            nodes = [str(node) for node in (row[0] or [])]
            amounts = [_numeric(value) for value in (row[1] or [])]
            timestamps = [_numeric(value, integer=True) for value in (row[2] or [])]
            target_confirmed_bad = bool(row[3]) if len(row) > 3 else False
            transfer_kinds = [str(value) for value in (row[4] or [])] if len(row) > 4 else []
            if not nodes or any(node is None for node in nodes) or any(value is None for value in amounts + timestamps):
                continue
            if not is_time_respecting_path(timestamps, window_seconds):
                continue
            paths.append(
                MoneyPathResult(
                    source_id=source_id,
                    target_id=str(nodes[-1]),
                    path_nodes=[str(node) for node in nodes],
                    amounts=[float(value) for value in amounts],
                    timestamps=[int(value) for value in timestamps],
                    is_time_ordered=True,
                    time_window_seconds=window_seconds,
                    target_confirmed_bad=target_confirmed_bad,
                    transfer_kinds=transfer_kinds,
                )
            )
        return paths

    def detect_transfer_cycles(
        self,
        entity_id: str,
        min_hops: int = 3,
        max_hops: int = 6,
        window_seconds: int = DEFAULT_CYCLE_WINDOW_SECONDS,
        limit: int = 50,
        window: Optional[int] = None,
    ) -> List[CycleResult]:
        if window is not None:
            window_seconds = window
        entity_id = _entity_id(entity_id)
        min_hops = _bounded_int("min_hops", min_hops, 3, MAX_HOPS)
        max_hops = _bounded_int("max_hops", max_hops, min_hops, MAX_HOPS)
        window_seconds = _bounded_int("window_seconds", window_seconds, 0, MAX_WINDOW_SECONDS)
        limit = _bounded_int("limit", limit, 1, MAX_RESULTS)
        cycles: list[CycleResult] = []
        # FalkorDB's variable-length path projection is version-sensitive: in
        # the pinned spike, relationship lists were returned in storage order
        # rather than traversal order.  Explicit bounded hops keep the graph
        # query authoritative while making the temporal sequence unambiguous.
        for hop_count in range(min_hops, max_hops + 1):
            node_aliases = [f"n{i}" for i in range(hop_count)]
            rel_aliases = [f"r{i}" for i in range(hop_count)]
            pattern = f"(n0:Account {{id: $entity_id}})"
            for index in range(hop_count):
                target = "n0" if index == hop_count - 1 else f"n{index + 1}"
                pattern += f"-[r{index}:SENT_MONEY]->({target}:Account)"
            query = f"""
            MATCH {pattern}
            RETURN [{', '.join(node_aliases)}] AS cycle_nodes,
                   [{', '.join(rel_aliases)}] AS cycle_relationships
            LIMIT $limit
            """
            result = self._query(query, {"entity_id": entity_id, "limit": max(1, limit - len(cycles))})
            for row in getattr(result, "result_set", []) or []:
                if len(row) < 2:
                    continue
                node_values = row[0] or []
                relationship_values = row[1] or []
                nodes = [str(getattr(node, "properties", {}).get("id")) for node in node_values]
                amounts = [_numeric(getattr(rel, "properties", {}).get("amount")) for rel in relationship_values]
                timestamps = [_numeric(getattr(rel, "properties", {}).get("ts"), integer=True) for rel in relationship_values]
                if any(value is None for value in amounts + timestamps) or len(timestamps) < min_hops:
                    continue
                # This is deliberately the only temporal decision.  In
                # particular, there is no reverse-unrolling or list reversal.
                if not is_time_respecting_cycle(timestamps, window_seconds):
                    continue
                cycles.append(
                    CycleResult(
                        entity_id=entity_id,
                        cycle_nodes=nodes,
                        amounts=[float(value) for value in amounts],
                        timestamps=[int(value) for value in timestamps],
                        is_time_ordered=True,
                        time_window_seconds=window_seconds,
                    )
                )
                if len(cycles) >= limit:
                    return cycles
        return cycles
