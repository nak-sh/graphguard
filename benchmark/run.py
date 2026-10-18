"""Measured FalkorDB versus SQLite recursive-CTE benchmark.

The command emits JSON only after real measurements. It never embeds latency
numbers in documentation. FalkorDB remains the graph source for the product;
SQLite is a deliberately separate comparator for the same transfer edges.
"""

from __future__ import annotations

import json
import os
import statistics
import time
from pathlib import Path
from typing import Any, Callable, Iterable

from falkordb import FalkorDB

from data.generate_demo import build_fixture


ROOT = Path(__file__).resolve().parents[1]
ARTIFACT_DIR = ROOT / "artifacts"


def percentile(samples: list[float], fraction: float) -> float:
    ordered = sorted(samples)
    if not ordered:
        return 0.0
    index = min(len(ordered) - 1, max(0, int(round((len(ordered) - 1) * fraction))))
    return ordered[index]


def measure(call: Callable[[], Any], *, warmups: int = 5, iterations: int = 30) -> dict[str, float | int]:
    for _ in range(warmups):
        call()
    samples: list[float] = []
    for _ in range(iterations):
        started = time.perf_counter()
        call()
        samples.append((time.perf_counter() - started) * 1000)
    return {"iterations": iterations, "warmups": warmups, "p50_ms": round(percentile(samples, 0.50), 4), "p95_ms": round(percentile(samples, 0.95), 4), "min_ms": round(min(samples), 4), "max_ms": round(max(samples), 4), "mean_ms": round(statistics.mean(samples), 4)}


def sqlite_connection(edges: Iterable[dict[str, Any]]):
    import sqlite3

    connection = sqlite3.connect(":memory:")
    connection.execute("CREATE TABLE transfer(source TEXT NOT NULL, target TEXT NOT NULL, amount REAL NOT NULL, ts INTEGER NOT NULL, PRIMARY KEY(source, target, ts))")
    connection.execute("CREATE INDEX transfer_source_ts ON transfer(source, ts)")
    connection.executemany("INSERT INTO transfer(source,target,amount,ts) VALUES(?,?,?,?)", [(row["source"], row["target"], row["amount"], row["ts"]) for row in edges])
    connection.commit()
    return connection


def sqlite_paths(connection: Any, source: str, max_hops: int) -> list[tuple[str, int]]:
    query = """
    WITH RECURSIVE walk(source, node, depth, path) AS (
      SELECT source, target, 1, '|' || source || '|' || target || '|'
      FROM transfer WHERE source = ?
      UNION ALL
      SELECT walk.source, transfer.target, walk.depth + 1,
             walk.path || transfer.target || '|'
      FROM walk JOIN transfer ON transfer.source = walk.node
      WHERE walk.depth < ? AND instr(walk.path, '|' || transfer.target || '|') = 0
    )
    SELECT node, depth FROM walk
    """
    return list(connection.execute(query, (source, max_hops)))


def build_sql_edges(fixture: dict[str, Any], size: int) -> list[dict[str, Any]]:
    allowed = {row["id"] for row in fixture["accounts"][:size]}
    return [row for row in fixture["transfers"] if row["source"] in allowed and row["target"] in allowed]


def seed_benchmark_graph(db: FalkorDB, name: str, fixture: dict[str, Any], size: int):
    graph = db.select_graph(name)
    try:
        graph.delete()
    except Exception:
        pass
    account_rows = fixture["accounts"][:size]
    edges = build_sql_edges(fixture, size)
    graph.query("UNWIND $rows AS row MERGE (a:Account {id: row.id}) SET a += row", {"rows": account_rows})
    graph.query(
        "UNWIND $rows AS row MATCH (source:Account {id: row.source}), (target:Account {id: row.target}) MERGE (source)-[r:SENT_MONEY {id: row.id}]->(target) SET r.amount=row.amount, r.ts=row.ts",
        {"rows": edges},
    )
    return graph


def run_benchmark(*, iterations: int = 30) -> dict[str, Any]:
    fixture = build_fixture(seed=int(os.getenv("GRAPHGUARD_SEED", "20241018")), noise_accounts=max(100, int(os.getenv("GRAPHGUARD_NOISE_ACCOUNTS", "1000"))))
    db = FalkorDB(host=os.getenv("GRAPHGUARD_DB_HOST", "localhost"), port=int(os.getenv("GRAPHGUARD_DB_PORT", "6379")))
    graph = db.select_graph(os.getenv("GRAPHGUARD_GRAPH_NAME", "graphguard"))
    results: list[dict[str, Any]] = []
    for size in (100, 500, len(fixture["accounts"])):
        edges = build_sql_edges(fixture, size)
        sqlite = sqlite_connection(edges)
        graph = seed_benchmark_graph(db, f"graphguard_bench_{size}", fixture, size)
        for depth in (2, 3, 4, 5):
            sqlite_metric = measure(lambda depth=depth: sqlite_paths(sqlite, "A-104", depth), iterations=iterations)
            graph_metric = measure(lambda depth=depth: graph.query(f"MATCH p=(a:Account {{id: $entity_id}})-[:SENT_MONEY*1..{depth}]->(b) RETURN count(p)", {"entity_id": "A-104"}), iterations=iterations)
            results.append({"size": size, "depth": depth, "query": "bounded_transfer_paths", "falkordb": graph_metric, "sqlite_recursive_cte": sqlite_metric, "sql_edges": len(edges)})
        sqlite.close()
        try:
            graph.delete()
        except Exception:
            pass
    output = {"schema_version": 1, "seed": fixture["config"]["seed"], "iterations": iterations, "warmups": 5, "methodology": "Client round-trip milliseconds; five warmups discarded; p50/p95 use nearest-rank index; same seeded transfer rows for each size.", "results": results}
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    (ARTIFACT_DIR / "benchmark.json").write_text(json.dumps(output, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return output


if __name__ == "__main__":
    print(json.dumps(run_benchmark(), indent=2, sort_keys=True))
