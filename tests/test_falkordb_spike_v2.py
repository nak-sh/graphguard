"""M0 FalkorDB syntax and client-shape spike.

These tests intentionally use the same pinned graph forms that the product
uses. They are skipped when FalkorDB is not reachable so pure unit tests stay
useful offline; Compose/CI runs them with the database service.
"""

import socket

import pytest

from apps.graph_tools.tools import GraphTools


def _graph_or_skip() -> GraphTools:
    sock = socket.socket()
    sock.settimeout(0.5)
    try:
        if sock.connect_ex(("127.0.0.1", 6379)) != 0:
            pytest.skip("FalkorDB is not reachable on localhost:6379")
    finally:
        sock.close()
    return GraphTools()


def test_pinned_query_forms_and_scenario_semantics():
    tools = _graph_or_skip()
    assert tools.g.query("RETURN 1 AS one").result_set == [[1]]

    indexes = tools.g.query("CALL db.indexes()").result_set
    assert any(row and row[0] == "Account" for row in indexes)

    cycles = tools.detect_transfer_cycles("A-104")
    assert cycles and cycles[0].cycle_nodes[0] == "A-104"
    assert cycles[0].timestamps == sorted(cycles[0].timestamps)

    assert tools.detect_transfer_cycles("D-201") == []
    assert tools.detect_transfer_cycles("D4-401") == []

    office_ip = tools.find_shared_ips("D3-001")
    assert office_ip and office_ip[0].is_hub is True
    assert office_ip[0].hub_degree == 40

    paths = tools.trace_money_paths("T2-201", max_hops=5, limit=10)
    assert paths and paths[-1].path_nodes[-1] == "T2-206"
    assert all(path.timestamps == sorted(path.timestamps) for path in paths)

    neighborhood = tools.get_neighborhood("A-104", max_hops=2, limit=100)
    assert neighborhood.nodes and neighborhood.edges
    assert len({(edge.source, edge.target, edge.relationship, edge.properties.get("id")) for edge in neighborhood.edges}) == len(neighborhood.edges)


def test_parameterized_limit_and_map_projection_are_supported():
    tools = _graph_or_skip()
    rows = tools.g.query(
        "MATCH (a:Account) RETURN {id: a.id, status: a.status} AS account LIMIT $limit",
        {"limit": 1},
    ).result_set
    assert len(rows) == 1
    assert rows[0][0]["id"]
