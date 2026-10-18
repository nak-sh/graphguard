# GraphGuard v2 audit

**Audit date:** 2026-10-18  
**Source reviewed:** `GraphGuard_v2_Concept_and_Architecture.docx` (Version 2, refined) and the extracted `graphguard-main` prototype.  
**Status:** Pre-implementation audit. No application code was changed while this document was created.

## Executive summary

The supplied repository is a small v1-style FastAPI/LangGraph/FalkorDB prototype with a Streamlit screen. It has a useful starting boundary between graph tools, scoring, workflow, actions, API, and UI, but it does not yet satisfy the v2 contract. The largest gaps are reproducibility, evidence/provenance, safe server-enforced actions, the real agent loop, scenario breadth, benchmark honesty, and the complete web product.

FalkorDB is already the only graph store used by the core prototype. The v2 implementation must preserve and strengthen that property: traversals, cycle detection, shared-infrastructure analysis, incidents, evidence, audit events, and action verification must remain graph-backed. No relational or in-memory substitute may become the source of truth.

## Current repository inventory

```text
README.md
requirements.txt
docker-compose.yml
apps/
  actions/executor.py
  agent/state.py
  agent/workflow.py
  api/main.py
  graph_tools/models.py
  graph_tools/tools.py
  policy/scorer.py
  web/app.py                 # Streamlit
benchmark/run.py
data/generate_demo.py
  test_cypher_spike.py
  test_phase2.py
  test_phase3.py
  test_phase4.py
```

Missing from the target layout are `mock_gateway`, `mcp_server`, a versioned policy file, a JavaScript frontend, API contracts, fixtures, evaluation output, benchmark output, CI configuration, `.env.example`, and the required `docs/` files (this audit and decisions log are the first additions).

## Existing behavior versus v2 requirements

### Graph tools and data

| Area | Current state | v2 requirement | Gap |
|---|---|---|---|
| Graph database | `GraphTools` connects to FalkorDB and selects `graphguard`. | FalkorDB is essential and pinned. | Image is `latest`; host, port, and graph are hard-coded. |
| Neighborhood | Variable-length undirected query exists. | Bounded, deduplicated, hub-aware UI subgraph with depth/result/timeout limits. | Hops are interpolated into Cypher, edges are duplicated, hubs are not pruned, and the query is not used by the workflow. |
| Shared infrastructure | Device-only query exists. | Device and IP analysis, non-hub signal, explicit hub handling. | `USED_IP` is never analyzed; `is_shared_hub` is not consistently seeded or queried. |
| Transfer paths | Not implemented. | Time-respecting bounded money paths. | Missing tool and contract. |
| Transfer cycles | Variable-length cycle query exists, then Python accepts monotonic forward **or backward** order and reverses results. | Rotation-invariant time-respecting test: at most one timestamp descent around the cycle, with a configurable max-minus-min window. | Current reverse-unrolling logic creates false positives and corrupts node order; no window parameter. |
| Query safety | Some entity values are parameters. | All inputs validated/allowlisted; depth, result, window, timeout and query budget caps. | Range values are interpolated and there are no central limits/timeouts. |
| FalkorDB syntax | A small smoke test runs two schematic queries. | Every used query/procedure must be verified against the pinned image and recorded. | No pinned image or `docs/VERIFIED_SYNTAX.md`; procedure/client result shapes are unverified. |

### Scoring and evidence

| Area | Current state | v2 requirement | Gap |
|---|---|---|---|
| Scoring | Hard-coded Python scorer supports cycle +40, device cluster +25, and one household mitigator. | Versioned deterministic full signal table. | Missing rapid pass-through, confirmed-bad proximity, IP +10, payroll -20, household conditions, policy version and stored evidence input. |
| Ring threshold | T1 scores 65 and tests accept `>=65`. | T1 must legitimately reach at least 70 and be hold-eligible. | Threshold defect is hidden by a relaxed test. |
| Evidence | Pydantic `EvidenceItem` exists but workflow stores incomplete raw dicts. | Stable evidence items persisted as `Evidence` nodes and linked to incidents/entities. | No persistence, result hashes, provenance links, or grounding validator. |
| Grounding | README claims strict grounding. | Every ID, amount and path in narrative must exist in evidence or be blocked/regenerated. | No LLM, narrative contract, or grounding check. |
| Non-escalation | All low scores use the generic “Decoys respected” message. | Explain checked signals, thresholds, and mitigators for each benign entity. | Missing `explain_non_escalation` tool and output. |

### Workflow and agent

| Area | Current state | v2 requirement | Gap |
|---|---|---|---|
| Orchestration | Fixed three-node LangGraph pipeline. | Loop with checkpointing, stopping rules, step/token budgets, and human approval interrupt. | `step_budget` and `visited_tools` are inert; no LLM/provider abstraction, checkpoint, loop, or interrupt. |
| LLM boundary | No model integration. | LLM may choose read-only tools and write grounded narrative only. | Missing Anthropic/OpenAI/none abstraction and deterministic offline playbook. |
| Alert validation | `alert_id` is accepted but not checked. | Alert and entity must be validated and linked. | Missing alert API/data validation. |
| Streaming | `/api/investigate` returns only final JSON. | SSE progress stream with tool steps and outcomes. | Missing event model and endpoint. |

### Actions, policy, and audit

| Area | Current state | v2 requirement | Gap |
|---|---|---|---|
| Action targets | Planner proposes only the flagged account. | Cover cycle members and non-hub shared-infrastructure members, classified by tier. | Affected-account expansion and policy classification are missing. |
| Dry run | Previous status is hard-coded to `ACTIVE`. | Read exact current FalkorDB state; no writes; exact per-node diff. | Defect present. |
| Server policy gate | API trusts client-supplied target/type. | Action must be proposed by stored incident, match policy tier/approval, caps, cooldowns and autonomy mode. | No incident linkage or enforcement. |
| Mock gateway | Missing. | Idempotent holds/releases with visible request log. | Missing service and integration. |
| Idempotency | Key is generated but never checked. | Duplicate key returns the original result and does not mutate twice. | Defect present. |
| Verification | Executor re-queries one status. | Gateway and graph verification with mismatch reporting. | Incomplete and not incident-wide. |
| Rollback | Restores stored previous state without conflict check; repeated rollback is unsafe; rollback audit reads status after `SET`. | Conflict-aware, idempotent compensating action with exact graph-diff proof. | Defects present. |
| Provenance | Basic `AuditEvent` is created by executor. | Incident/Evidence/AuditEvent graph nodes, links, actor, policy and tamper-evident chain. | Missing incident/evidence nodes and hash chain. |
| Audit API | No GET endpoints. | Alerts, incidents, audit list and chain verification. | Missing. |

### Data, evaluation, and benchmark

| Area | Current state | v2 requirement | Gap |
|---|---|---|---|
| Seed data | T1 ring and D1 family decoy only. | T1–T3, D1–D4, background noise, fixed seed, ground truth outside graph. | Six scenarios and scale data missing. |
| Hub handling | T1 has a shared device but no complete hub metadata model. | Device/IP hubs are explicit and excluded from traversal by default. | Missing scenario D3 and deterministic hub flagging. |
| Evaluation | No scenario harness. | One command reports detection tier, zero decoy escalations, evidence traceability, grounding, idempotency, rollback fidelity. | Missing. |
| Benchmark | One tiny FalkorDB query and hand-selected p50/p95 indexes. | FalkorDB versus SQLite recursive CTE (optionally Postgres), multiple sizes/depths, warm-up, 30+ runs, machine-readable output. | SQL baseline, scaling, correctness, metadata and reproducible output missing. |
| Claims | README contains hard-coded latency and SQL claims. | Only generated, reproducible measurements may be published. | Must be rewritten after benchmark exists. |

### Product and delivery

| Area | Current state | v2 requirement | Gap |
|---|---|---|---|
| Frontend | 80-line Streamlit page with two hard-coded entities. | Next.js interactive security-operations workspace. | Entire replacement missing. |
| Signature features | None beyond basic dry-run/rollback attempt. | B1–B4 required; B5–B8 expected after Tier 1; B9–B11 after M8. | Missing optimizer, replay, red-team, tamper chain, sandbox, autonomy dial, explorer, copilot and demo mode. |
| Compose | Starts only `falkordb/falkordb:latest`. | One command starts pinned FalkorDB, API, web, mock gateway. | Missing services, health checks, volumes and readiness. |
| Dependencies | Lower bounds only; `streamlit` and `requests` are missing despite imports. | Pinned reproducible dependencies and frontend lockfile. | Setup defect present. |
| Tests | All tests assume a pre-seeded live database and mutate shared state. | Unit, integration, API, frontend smoke and Docker Compose CI. | Fixtures, conftest, isolation, Playwright and CI missing. |
| Documentation | README only and contains unsupported claims. | README generated from result artifacts plus `VERIFIED_SYNTAX.md`, decisions, audit and demo script. | Documentation overhaul required. |

## Known defect confirmation

The supplied code confirms all user-listed defects:

1. Cycle temporal logic accepts forward/backward monotonic sequences and reverses node order.
2. T1 is scored at 65; the test masks the missing signal by accepting `>=65`.
3. Only the flagged entity is actioned.
4. Dry-run status is hard-coded to `ACTIVE`.
5. The execute route trusts client action data.
6. Idempotency keys are not looked up or enforced.
7. Rollback is not conflict-aware or safely idempotent and records state after mutation.
8. Scoring re-queries instead of scoring stored evidence.
9. Neighborhood output is duplicated, unbounded by hubs, and unused by the workflow.
10. IP data is seeded but never analyzed.
11. The workflow is fixed and has no LLM/tool-selection loop or fallback abstraction.
12. There is no grounding check or real non-escalation explanation.
13. Policy code, mock gateway, provenance nodes, GET endpoints, and SSE are missing.
14. Only T1 and D1 are seeded.
15. Benchmark is FalkorDB-only and README contains unmeasured SQL/performance claims.
16. Setup is incomplete: unpinned image/dependencies, missing imports, no full-stack compose, and BOM-prefixed `.gitignore`.
17. README claims capabilities that do not exist and lacks the required AI-assistant disclosure placeholder.

## Baseline checks run

At audit time the source was inspected statically. The current tests require FalkorDB to be running and seeded, so they are not evidence of a clean checkout. Before implementation, the following were not yet run successfully in a clean stack:

- `pytest -q`
- `python data/generate_demo.py`
- `docker compose up`
- `python benchmark/run.py`
- a frontend build (no frontend package exists)

The M0 spike will make those dependencies explicit, pin the FalkorDB image, run the query/client checks against that image, and record all verified syntax in `docs/VERIFIED_SYNTAX.md`.

## M0 acceptance criteria

M0 is complete only when:

1. The pinned FalkorDB image starts reproducibly and exposes a readiness check.
2. A spike runs every query form/procedure relied upon by the implementation, including client result-shape checks.
3. The spike proves T1 cycle/shared-device behavior and D1 non-cycle behavior.
4. Rotation-invariant cycle semantics, reverse false-positive rejection, and the time-window rule are represented by tests.
5. `docs/VERIFIED_SYNTAX.md` records exact commands, image/version, supported forms, and any rejected form/workaround.
6. `docs/DECISIONS.md` records choices and unresolved risks without presenting assumptions as facts.

Subsequent milestones must leave the app startable and tests runnable; a feature is not complete merely because an endpoint or button exists.
