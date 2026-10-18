# FalkorDB verified syntax

**Verification date:** 2026-10-18  
**Observed module:** FalkorDB graph module `ver=42201` (reported by Redis `MODULE LIST`, equivalent to 4.22.1).  
**Repository pin:** `falkordb/falkordb:v4.22.1` in `docker-compose.yml`.  
**Environment:** local FalkorDB on `localhost:6379`, seeded with `python data/generate_demo.py`.

This is an executable record, not a claim inferred from a generic Cypher reference. The M0 checks are in `tests/test_falkordb_spike_v2.py` and run against the configured graph service.

## Commands run

```text
python data/generate_demo.py
python -m pytest -q tests/test_falkordb_spike_v2.py
python -m pytest -q tests/test_cypher_spike.py tests/test_phase2.py
```

Observed result during M0:

```text
python data/generate_demo.py                         passed
tests/test_cypher_spike.py                           passed
tests/test_phase2.py                                 passed after the explicit-hop fix
tests/test_falkordb_spike_v2.py                      passed
```

## Verified forms used by GraphGuard

| Form | Status | Evidence |
|---|---|---|
| `RETURN 1 AS one` | Verified | M0 spike |
| `CALL db.indexes()` | Verified | M0 spike; returns Account, Device, IPAddress and Alert indexes after seed |
| `CREATE INDEX FOR (a:Account) ON (a.id)` | Verified by seed | Seed script completes against the observed module |
| Parameterized node lookup `MATCH (a:Account {id: $entity_id})` | Verified | GraphTools and M0 scenario queries |
| Parameterized `LIMIT $limit` | Verified | M0 map-projection test |
| `UNWIND $rows AS row` with `MERGE` and `SET n += row` | Verified | Seed completes and is idempotent |
| `labels(n)`, `properties(n)`, `type(r)`, `startNode(r)`, `endNode(r)` | Verified | Neighborhood map projection and M0 result assertions |
| Explicit directed paths with aliased nodes and relationships | Verified | `detect_transfer_cycles` and `trace_money_paths` |
| Variable-length read-only neighborhood traversal | Verified | `get_neighborhood` and M0 result assertions |
| `collect(DISTINCT other.id)` and `size(...)` | Verified | Shared device/IP tools and scenario assertions |

## Important compatibility finding

The first v2 implementation tried to filter variable-length cycles in Cypher with:

```cypher
max([r IN relationships(p) | r.ts]) - min([r IN relationships(p) | r.ts])
```

Against the observed FalkorDB module this failed with:

```text
Type mismatch: expected Datetime, Date, Time, Duration, Integer, Float, or Null but was Unknown
```

GraphGuard therefore does **not** rely on that list aggregate. The final cycle tool uses explicit bounded directed hops (3 through 6), returns relationship objects in alias order, and performs the rotation-invariant temporal predicate in tested Python code. This preserves FalkorDB as the source of the paths and avoids unverified procedure behavior.

The same principle is used for money paths: FalkorDB applies the directed traversal and amount bound, while the tested Python boundary validates chronological order and the max-minus-min time window.

## Client result-shape finding

The installed Python client exposes `Path.nodes()` and `Path.edges()`, but the observed variable-length path object order did not align reliably with the server-side projected relationship order. GraphGuard uses scalar/map projections for cycle, path, and neighborhood normalization instead of treating the client `Path` object as an authoritative ordered edge list.

## Not relied upon

No built-in FalkorDB algorithm procedure is required by the current core. A future optional algorithm must first be added to the spike, verified on the pinned image, and documented here before use. `CALL db.version()` was not registered on the observed module and is not used for runtime behavior.
