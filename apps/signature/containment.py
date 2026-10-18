"""Smallest-safe-freeze optimizer over evidence fetched from FalkorDB."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Mapping, Sequence

import networkx as nx


@dataclass(frozen=True)
class AccountCost:
    account_id: str
    monthly_volume: float = 0.0
    legit_activity: float = 0.0

    @property
    def collateral_cost(self) -> float:
        return max(self.monthly_volume, 1.0) * (0.25 + max(0.0, min(1.0, self.legit_activity)))


def _cycle_accounts(cycle: Any) -> list[str]:
    if hasattr(cycle, "cycle_nodes"):
        return [str(value) for value in cycle.cycle_nodes[:-1]]
    return [str(value) for value in cycle.get("cycle_nodes", [])[:-1]]


def _path_edges(paths: Sequence[Any]) -> list[tuple[str, str]]:
    edges: list[tuple[str, str]] = []
    for path in paths:
        nodes = list(getattr(path, "path_nodes", path.get("path_nodes", []) if isinstance(path, Mapping) else []))
        edges.extend((str(a), str(b)) for a, b in zip(nodes, nodes[1:]))
    return edges


def _greedy_hitting_set(cycles: Sequence[Sequence[str]], costs: Mapping[str, AccountCost]) -> list[str]:
    remaining = [set(cycle) for cycle in cycles if cycle]
    selected: list[str] = []
    while remaining:
        candidates = set().union(*remaining)
        choice = min(
            candidates,
            key=lambda account: (
                costs.get(account, AccountCost(account)).collateral_cost / max(sum(account in cycle for cycle in remaining), 1),
                account,
            ),
        )
        selected.append(choice)
        remaining = [cycle for cycle in remaining if choice not in cycle]
    return selected


def _mule_cut(paths: Sequence[Any], costs: Mapping[str, AccountCost]) -> list[str]:
    graph = nx.DiGraph()
    for source, target in _path_edges(paths):
        graph.add_edge(source, target, capacity=1.0)
    if graph.number_of_edges() == 0:
        return []
    source = next(iter(graph.nodes))
    target = list(graph.nodes)[-1]
    if source == target or not nx.has_path(graph, source, target):
        return []
    # NetworkX computes the cut on the fetched FalkorDB subgraph; FalkorDB
    # remains authoritative for which edges were fetched.
    _, partition = nx.minimum_cut(graph, source, target, capacity="capacity")
    left, right = partition
    boundary = [u for u in left for v in graph.successors(u) if v in right]
    return sorted(set(boundary), key=lambda account: costs.get(account, AccountCost(account)).collateral_cost)


def optimize_containment(
    cycles: Sequence[Any],
    paths: Sequence[Any] = (),
    account_properties: Mapping[str, Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Compare hold-all, greedy cycle hitting set, and flag-only options."""

    account_properties = account_properties or {}
    costs = {
        account_id: AccountCost(
            account_id,
            float(properties.get("monthly_volume", 0.0)),
            float(properties.get("legit_activity_ratio", properties.get("legit_activity", 0.0) or 0.0)),
        )
        for account_id, properties in account_properties.items()
    }
    cycle_sets = [_cycle_accounts(cycle) for cycle in cycles]
    cycle_accounts = sorted(set().union(*[set(cycle) for cycle in cycle_sets]) if cycle_sets else set())
    path_accounts = sorted(set().union(*[set(edge) for edge in _path_edges(paths)]) if paths else set())
    all_hold = sorted(set(cycle_accounts) | set(path_accounts))
    optimized = _greedy_hitting_set(cycle_sets, costs)
    if paths:
        optimized = sorted(set(optimized) | set(_mule_cut(paths, costs)))

    def metrics(accounts: Sequence[str]) -> dict[str, Any]:
        selected = set(accounts)
        suspicious_volume = sum(float(account_properties.get(account, {}).get("monthly_volume", 0.0)) for account in selected)
        legitimate_volume = sum(
            float(account_properties.get(account, {}).get("monthly_volume", 0.0))
            * float(account_properties.get(account, {}).get("legit_activity_ratio", 0.0) or 0.0)
            for account in selected
        )
        return {
            "accounts": list(accounts),
            "account_count": len(accounts),
            "suspicious_volume_interrupted_estimate": round(suspicious_volume, 2),
            "legitimate_volume_frozen_estimate": round(legitimate_volume, 2),
        }

    return {
        "synthetic_estimates": True,
        "method": "greedy weighted cycle hitting-set plus NetworkX min-cut over FalkorDB-fetched paths",
        "hold_all": metrics(all_hold),
        "hold_optimizer_pick": metrics(optimized),
        "flag_only": metrics([]),
        "detected_cycle_count": len(cycle_sets),
        "path_edge_count": len(_path_edges(paths)),
    }
