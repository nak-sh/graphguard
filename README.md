# GraphGuard

GraphGuard is a synthetic-data fraud investigation and safe-response workspace for **Graph Hacks: Context for AI Agents, Track 1: Agents That Act on Connected Data**.

It investigates suspicious accounts through FalkorDB-backed neighborhoods, shared devices/IPs, directed money paths, and time-respecting transfer cycles. A deterministic scorer and policy engine turn the evidence into a review/hold proposal. The LLM boundary, when configured, may choose the next **read-only** tool and draft language; it is never the source of relationships, scores, permissions, or mutations.

> **Synthetic data:** every account, transfer, finding, score, and action in this repository is fictional and deterministic. A graph relationship is a lead, not proof of fraud.

## What is verifiably implemented

- FalkorDB is the graph source of truth for traversals, cycle detection, infrastructure analysis, incidents, evidence, actions, and audit events.
- T1–T3 positive scenarios and D1–D4 benign/look-alike scenarios are seeded with a fixed seed, ground-truth labels, and deterministic background noise.
- Cycle ordering is rotation-invariant: the circular timestamp sequence may contain at most one descent and must fit the configured max-minus-min window. The path is never reverse-unrolled.
- Evidence is normalized into stable IDs, persisted as `Evidence` nodes, linked to `Incident` nodes, and passed unchanged to the scorer.
- Dry runs read real account state from FalkorDB and show exact from/to changes without writing.
- Actions are stored-incident-only, policy-tier checked, approval-gated, idempotent, gateway-visible, verified by graph re-query, and rollbackable with conflict detection.
- Audit events form a SHA-256 chain. `GET /api/audit/verify` detects tampering; the tamper control is disabled unless `GRAPHGUARD_DEV_CONTROLS=1`.
- The offline deterministic playbook completes the demo without an LLM key. Anthropic and OpenAI-compatible structured tool selection are optional adapters.
- `mcp_server/server.py` exposes the same read-only tools and dry-run contract; execution requires an explicit approval token. The MCP SDK is an optional separate process so its major-version transport dependencies cannot silently change the FastAPI stack.
- The Next.js web app provides a shared security-operations shell with live health/autonomy state, API-offline empty states, a Cytoscape/fcose neighborhood graph, SSE investigation progress, evidence/score/why/actions/copilot tabs, approval-gated dry runs, rollback, gateway logs, audit verification, command palette, and dedicated replay, containment, red-team, policy, audit, and benchmark views.
- `make eval` and `make benchmark` write machine-readable result artifacts; this README does not contain hand-entered latency or accuracy figures.

## Architecture

```text
Next.js mission control ── typed HTTP/SSE ── FastAPI
                                             │
                         LangGraph loop ─────┤ read-only tool choice
                                             │
                  deterministic scoring/policy/actions
                                             │
                 FalkorDB ───── mock payment gateway
                    │  │  │              │
          entities / evidence / incidents / audit chain
```

### Repository layout

```text
apps/graph_tools/       strict contracts and the only FalkorDB read boundary
apps/policy/            versioned YAML policy and evidence-only scorer
apps/agent/             LangGraph loop, provider adapter, fallback, grounding
apps/actions/           dry-run, policy gate hooks, gateway, audit, rollback
apps/signature/         containment optimizer, replay, red-team matrix
apps/api/               FastAPI routes and SSE stream
mock_gateway/           idempotent FastAPI mock gateway plus in-process contract
evaluation/             scenario/evidence/grounding/action harness
benchmark/              FalkorDB versus SQLite recursive-CTE measurements
web/                    Next.js App Router frontend
```

## Why a graph, honestly

GraphGuard needs directed multi-hop paths, typed infrastructure relationships, and circular transfer checks over a connected network. The repository also includes a SQLite recursive-CTE comparator because a graph claim should be measured rather than assumed. Run:

```bash
make benchmark
```

The command writes `artifacts/benchmark.json`, including the seed, graph sizes, depths, warm-ups, iteration count, p50 and p95 for both engines, and methodology. Results can be competitive for SQL at small sizes; GraphGuard does not promise a win before measuring.

The exact FalkorDB forms used by the implementation are recorded in [`docs/VERIFIED_SYNTAX.md`](docs/VERIFIED_SYNTAX.md). The pinned image is `falkordb/falkordb:v4.22.1`.

## Graph data model

```text
(:Alert)-[:ABOUT]->(:Account)
(:Account)-[:USES_DEVICE]->(:Device)
(:Account)-[:USED_IP]->(:IPAddress)
(:Account)-[:SENT_MONEY {id, amount, ts}]->(:Account)
(:Incident)-[:SUPPORTED_BY]->(:Evidence)-[:REFERENCES]->(:Account|:Device|:IPAddress)
(:Incident)-[:HAS_ACTION]->(:AuditEvent)-[:TARGETED]->(:Account)
```

Transfers are edges, not transaction nodes, so the exact directed path remains easy to inspect and audit. Device/IP nodes carry explicit hub metadata. Account fixtures include synthetic monthly volume and legitimate-activity estimates for the containment trade-off view.

## Key queries actually used

The core tools use parameterized IDs and validated integer bounds. Cycle and path tools use explicit bounded relationship aliases because the M0 spike found that variable-length path projections were not ordered reliably on the observed client/module combination.

```cypher
MATCH (n0:Account {id: $entity_id})
      -[r0:SENT_MONEY]->(n1:Account)
      -[r1:SENT_MONEY]->(n2:Account)
      -[r2:SENT_MONEY]->(n0)
RETURN [n0, n1, n2] AS cycle_nodes,
       [r0, r1, r2] AS cycle_relationships
LIMIT $limit
```

Shared infrastructure, neighborhood, and money-path projections are visible in `apps/graph_tools/tools.py`; every input is bounded or allowlisted before query construction.

## Scenarios and evaluation

| Scenario | Expected disposition | Purpose |
|---|---|---|
| T1 | AUTO_HOLD | Five-account time-ordered ring with non-hub shared device |
| T2 | MANUAL_REVIEW | Directed mule chain reaching a synthetic confirmed-bad anchor |
| T3 | MANUAL_REVIEW | Synthetic identity cluster with shared device and IP |
| D1 | NO_ACTION | Two-account household/shared device with small mutual transfers |
| D2 | NO_ACTION | Payroll-style one-to-many fan-out without return flow |
| D3 | NO_ACTION | Shared office IP/device hub with approximately forty accounts |
| D4 | NO_ACTION | Out-of-order coincidental loop |

Run the real harness:

```bash
make eval
```

The generated [`artifacts/eval.json`](artifacts/eval.json) reports each disposition, signal rules, evidence traceability, grounding violations, false escalations, idempotency, and rollback-fidelity checks. A clean run requires zero decoy escalations and zero grounding violations.

## Setup

Prerequisites: Docker Compose, Python 3.11+, and Node.js 20+ for local frontend development.

```bash
cp .env.example .env
python -m venv .venv
# Windows: .venv\\Scripts\\activate
# Linux/macOS: source .venv/bin/activate
pip install -r requirements.txt

docker compose up --build -d
```

The Compose `seed` service waits for FalkorDB and loads the deterministic graph before the API starts. Open the frontend at `http://localhost:3000`. The FastAPI health endpoint is `http://localhost:8000/health`; the FalkorDB Browser is mapped to `http://localhost:3002`.

Useful checks:

```bash
make test
make syntax
make eval
make benchmark
make demo
```

The Python app can also run locally with:

```bash
uvicorn apps.api.main:app --reload
cd web && npm install && npm run dev
```

The frontend defaults to the `/backend` rewrite in `web/next.config.mjs`; set `NEXT_PUBLIC_API_BASE_URL` when serving it behind a different proxy.

## Signature features

- **Containment optimizer:** greedy weighted hitting set over detected cycles plus NetworkX min-cut over the FalkorDB-fetched path subgraph; compares hold-all, optimizer pick, and flag-only with synthetic collateral estimates.
- **Time-travel replay:** returns edges sorted by timestamp with cumulative volume and a cycle-close frame for the timeline scrubber.
- **Red-team lab:** shows baseline and evasion variants honestly, including misses and the policy knob that could address each one. Scratch-graph execution is isolated from the demo graph.
- **Tamper-evident audit:** SHA-256 event chaining, verification endpoint, and a disabled-by-default dev tamper control.

## Safety and limitations

- No real customer data, bank integration, money movement, account freeze, or definitive fraud adjudication is present.
- The mock gateway changes only synthetic graph state. It is not a payment processor.
- The LLM is optional and non-authoritative. Provider failure falls back to the deterministic read-only playbook.
- Collateral volume and legitimate-activity values are synthetic estimates, not operational risk measurements.
- The benchmark measures local client round trips and is not a production capacity guarantee.
- The web graph canvas renders only the API neighborhood response, caps the client renderer at 300 nodes, and reports hidden-node counts when the backend returns a larger result. It never substitutes a demo graph when the API is unavailable.

## AI-assistant disclosure

GraphGuard was built with AI assistance, directed, written in significant part, and
reviewed by me.

**Tools used:** Claude (Anthropic), ChatGPT / an OpenAI coding agent, and Gemini (Google).

**What the AI assistants did**
- Claude: analysed the hackathon tracks, helped refine the problem statement,
  drafted the architecture/design document, reviewed code for defects, wrote
  implementation prompts, helped troubleshoot Docker and environment issues,
  and helped draft the README and submission text.
- Gemini: helped develop the initial version of the project (the first working
  prototype: FalkorDB setup, first graph tools, scoring, agent workflow, and
  Streamlit UI), which I then reviewed and built on.
- ChatGPT / coding agent: generated much of the later implementation from the
  design document and my prompts, including the frontend rebuild and
  extensions to the backend.

**What I did**
- Chose the problem, the track, and the overall scope and feature priorities.
- Specified the requirements and the safety design (dry-run, approval gates,
  rollback, audit chain, decoy scenarios).
- Backend and graph tools (the largest part of my hands-on work): [e.g. wrote
  and debugged the Cypher queries and graph tools, the scoring logic, the
  scenario/decoy data, and the action and rollback logic; fixed the cycle
  time-ordering bug and the FalkorDB path-ordering issue].
- Frontend (smaller part): [e.g. reviewed the UI, tested the flows, and made
  some edits to components and layout].
- Reviewed generated code, found defects, and had them fixed or fixed them
  myself.
- Ran the stack locally with Docker, tested the scenarios, and resolved setup
  and deployment problems.
- Made the final decisions on what to include, claim, and submit.

All scenario data is synthetic. Evaluation and benchmark numbers in this repo
are produced by the included scripts, not written by hand.
