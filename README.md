# GraphGuard

GraphGuard is a synthetic-data fraud investigation and safe-response workspace for **Graph Hacks: Context for AI Agents, Track 1: Agents That Act on Connected Data**.

It investigates suspicious accounts through FalkorDB-backed neighborhoods, shared devices/IPs, directed money paths, and time-respecting transfer cycles. A deterministic scorer and policy engine turn the evidence into a review/hold proposal. The LLM boundary, when configured, may choose the next read-only tool and draft language; it is never the source of relationships, scores, permissions, or mutations.

> **Synthetic data:** every account, transfer, finding, score, and action in this repository is fictional and deterministic. A graph relationship is a lead, not proof of fraud.

## Quick start

```bash
git clone https://github.com/nak-sh/graphguard.git
cd graphguard
cp .env.example .env          # Windows PowerShell: copy .env.example .env
docker compose up --build -d
```

Then open **http://localhost:3000**. No API key is required. See [Setup](#setup) for verification steps, the demo walkthrough, and troubleshooting.

## What is verifiably implemented

- FalkorDB is the graph source of truth for traversals, cycle detection, infrastructure analysis, incidents, evidence, actions, and audit events.
- T1–T3 positive scenarios and D1–D4 benign/look-alike scenarios are seeded with a fixed seed, ground-truth labels, and deterministic background noise.
- Cycle ordering is rotation-invariant: the circular timestamp sequence may contain at most one descent and must fit the configured max-minus-min window. The path is never reverse-unrolled.
- Evidence is normalized into stable IDs, persisted as Evidence nodes, linked to Incident nodes, and passed unchanged to the scorer.
- Dry runs read real account state from FalkorDB and show exact from/to changes without writing.
- Actions are stored-incident-only, policy-tier checked, approval-gated, idempotent, gateway-visible, verified by graph re-query, and rollbackable with conflict detection.
- Audit events form a SHA-256 chain. `GET /api/audit/verify` detects tampering; the tamper control is disabled unless `GRAPHGUARD_DEV_CONTROLS=1`.
- The offline deterministic playbook completes the demo without an LLM key. Anthropic and OpenAI-compatible structured tool selection are optional adapters.
- `mcp_server/server.py` exposes the same read-only tools and dry-run contract; execution requires an explicit approval token. The MCP SDK is an optional separate process so its major-version transport dependencies cannot silently change the FastAPI stack.
- The Next.js web app provides a shared security-operations shell with live health/autonomy state, API-offline empty states, a Cytoscape/fcose neighborhood graph, SSE investigation progress, evidence/score/why/actions/copilot tabs, approval-gated dry runs, rollback, gateway logs, audit verification, command palette, and dedicated replay, containment, red-team, policy, audit, and benchmark views.
- `make eval` and `make benchmark` write machine-readable result artifacts; this README does not contain hand-entered latency or accuracy figures.

## Architecture

```
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

```
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

The exact FalkorDB forms used by the implementation are recorded in `docs/VERIFIED_SYNTAX.md`. The pinned image is `falkordb/falkordb:v4.22.1`.

## Graph data model

```
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

The generated `artifacts/eval.json` reports each disposition, signal rules, evidence traceability, grounding violations, false escalations, idempotency, and rollback-fidelity checks. A clean run requires zero decoy escalations and zero grounding violations. These are in-sample checks over seeded synthetic scenarios, not accuracy claims.

## Setup

### Prerequisites

- Docker Desktop (Compose v2), **running**
- Git
- Python 3.11+ (only for tests, evaluation, benchmark, or non-Docker development)
- Node.js 20+ (only for non-Docker frontend development)
- GNU Make is optional; every `make` target below has a plain command alternative

The first build downloads images and dependencies and can take several minutes.

### 1. Run everything with Docker (recommended)

```bash
cp .env.example .env          # Windows PowerShell: copy .env.example .env
docker compose up --build -d
```

Run Compose from the repository folder. The containers use fixed names (`graphguard-db`, `graphguard-api`, ...), so starting the project from two different copies will conflict.

Services and ports:

- `falkordb` — graph database (`localhost:6379`); FalkorDB Browser at http://localhost:3002
- `seed` — loads the deterministic graph, then exits (`Exited (0)` is expected)
- `api` — FastAPI backend at http://localhost:8000
- `mock-gateway` — mock payment gateway at http://localhost:8010
- `web` — Next.js frontend at **http://localhost:3000**

### 2. Check that it works

```bash
docker compose ps
```

- `falkordb`, `api`, `mock-gateway`, and `web` should be running; `seed` should show `Exited (0)`.
- http://localhost:8000/health should return `{"ok":true,"falkordb":true,"synthetic_data":true}`.
- http://localhost:3000/backend/health should return the same JSON (this confirms the frontend can reach the API).
- http://localhost:3000 should load with the top bar showing the API as connected, not offline.

### 3. Optional configuration

No API key is needed. Without one, the agent uses its deterministic offline playbook, which completes the full demo.

- **LLM tool selection (optional):** set `GRAPHGUARD_LLM_PROVIDER`, `GRAPHGUARD_LLM_MODEL`, and `GRAPHGUARD_LLM_API_KEY` (and `GRAPHGUARD_LLM_BASE_URL` for an OpenAI-compatible endpoint). See `apps/agent/providers.py` for the accepted provider values.
- **Tamper-simulation control (demo only):** set `GRAPHGUARD_DEV_CONTROLS=1`.

For the Docker stack, these variables must reach the `api` container. Put them in the `api` service `environment:` block in `docker-compose.yml` (or add `env_file: .env` there and keep the compose-defined `GRAPHGUARD_DB_HOST` value, which overrides the `localhost` default in `.env.example`), then recreate the container:

```bash
docker compose up -d --force-recreate api
```

### 4. Demo walkthrough (about 3 minutes)

1. Open http://localhost:3000 and select the **ring alert** (entity A-104) in the queue. Nothing result-like is shown until you run an investigation.
2. Run the investigation. Evidence, the score, the policy tier, and the proposed actions appear, and the detected transfer cycle is highlighted on the graph.
3. Open the **Actions** tab: run the dry run to see the exact from/to changes, approve it (policy requires approval for larger bulk holds), and execute with hold-to-confirm.
4. Check the **gateway request log** and **audit verification**, then press **Undo** and confirm the account statuses are restored.
5. Investigate the **household** (D-201) and **shared-office hub** alerts. Both should end in no action, with a "why not" explanation.
6. Visit the Replay, Containment, Red-Team, Policy, Audit, and Benchmark views, or run the **Guided Demo**.

See [`docs/DEMO_SCRIPT.md`](docs/DEMO_SCRIPT.md) for the 3–5 minute narrated version. The three strongest judge moments are the rotation-safe ring explanation, the visibly reversible action loop with gateway/audit verification, and the benign decoy/hub cases that the agent leaves alone with reasons.

### 5. Tests, evaluation, and benchmark

Create a Python environment and install the pinned dependencies (the stack must be running, because the tests and harness use FalkorDB on `localhost:6379`):

```bash
python -m venv .venv
# Windows:      .venv\Scripts\activate
# macOS/Linux:  source .venv/bin/activate
pip install -r requirements.txt
```

Then run:

```bash
make test        # python -m pytest -q
make syntax      # python -m pytest -q tests/test_falkordb_spike_v2.py
make eval        # python -m evaluation.run   (re-seeds the demo graph first)
make benchmark   # python -m benchmark.run    (re-seeds the demo graph first)
```

`make eval` and `make benchmark` re-seed the graph, which resets any demo state. Run the commands from the repository root; `make` is optional on Windows, so use the plain commands in the comments.

**The Benchmark page reads `artifacts/benchmark.json`**, which is generated and not committed. If the page is empty, generate it inside the API container so the API can read it:

```bash
docker compose exec api sh -c "mkdir -p artifacts && python -m benchmark.run"
```

### 6. Run without Docker for the app (development)

```bash
docker compose up -d falkordb
python data/generate_demo.py
uvicorn mock_gateway.app:app --port 8010
uvicorn apps.api.main:app --reload --port 8000
cd web && npm ci && npm run dev
```

Run the first four commands from the repository root with the virtual environment active, and the gateway and API in separate terminals. The frontend defaults to the `/backend` rewrite in `web/next.config.mjs`, which forwards to `http://localhost:8000`; set `GRAPHGUARD_API_URL` if the API runs elsewhere, or `NEXT_PUBLIC_API_BASE_URL` when serving the frontend behind a different proxy.

### 7. Reset and stop

```bash
docker compose up -d --force-recreate seed   # restore a clean demo graph
docker compose down                          # stop everything
docker compose down -v                       # stop and delete the database volume
docker compose logs -f api                   # follow logs (or web, seed, falkordb)
```

### Troubleshooting

- **"Container name already in use":** old containers remain from a previous run or folder. Remove them and start again:
  ```bash
  docker rm -f graphguard-db graphguard-mock-gateway graphguard-seed graphguard-api graphguard-web
  docker compose up -d
  ```
- **"Port is already allocated":** something else is using 3000, 3002, 6379, 8000, or 8010. Stop it, or change the host-side port in `docker-compose.yml`.
- **App shows "API offline":** open http://localhost:8000/health first. If that works, rebuild the web image (`docker compose build --no-cache web`) and recreate it. If it fails, check `docker compose logs api` and confirm `seed` finished.
- **Web container exits with `EAI_AGAIN` or a hostname error:** `HOSTNAME: "0.0.0.0"` must be set in the `web` service environment (it is in the shipped compose file).
- **Docker build fails with `invalid file request node_modules/.bin/...`:** delete `web/node_modules` and `web/.next` locally and make sure `web/.dockerignore` excludes them.
- **`No module named apps`:** run commands from the repository root and use `python -m pytest`.

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
- The benchmark measures local client round trips on small synthetic graphs and is not a production capacity guarantee.
- The evaluation covers seven seeded scenarios and is in-sample; it does not measure real-world detection accuracy.
- The web graph canvas renders only the API neighborhood response, caps the client renderer at 300 nodes, and reports hidden-node counts when the backend returns a larger result. It never substitutes a demo graph when the API is unavailable.
- The frontend is checked by typecheck, lint, and production build; there are no automated browser tests yet.

## AI-assistant disclosure

GraphGuard was built with AI assistance, directed, written in significant part, and reviewed by me.

**Tools used:** Claude (Anthropic), ChatGPT / an OpenAI coding agent, and Gemini (Google).

**What the AI assistants did**

- Claude: analysed the hackathon tracks, helped refine the problem statement, drafted the architecture/design document, reviewed code for defects, wrote implementation prompts, helped troubleshoot Docker and environment issues, and helped draft the README and submission text.
- Gemini: helped develop the initial version of the project (the first working prototype: FalkorDB setup, first graph tools, scoring, agent workflow, and Streamlit UI), which I then reviewed and built on.
- ChatGPT / coding agent: generated much of the later implementation from the design document and my prompts, including the frontend rebuild and extensions to the backend.

**What I did**

- Chose the problem, the track, and the overall scope and feature priorities.
- Specified the requirements and the safety design (dry-run, approval gates, rollback, audit chain, decoy scenarios).
- Backend and graph tools (the largest part of my hands-on work): I wrote, revised, and debugged a large share of the backend and graph-tool code, working alongside the AI-generated code.
- Frontend (a smaller part): I made some edits to the frontend and tested the UI flows.
- Reviewed generated code, found defects, and had them fixed or fixed them myself.
- Ran the stack locally with Docker, tested the scenarios, and resolved setup and deployment problems.
- Made the final decisions on what to include, claim, and submit.

All scenario data is synthetic. Evaluation and benchmark numbers in this repo are produced by the included scripts, not written by hand.
