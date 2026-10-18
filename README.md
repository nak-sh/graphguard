# GraphGuard: Graph-Augmented Fraud Investigation & Safe Response Agent

> Autonomous, evidence-grounded fraud investigation agent powered by FalkorDB, LangGraph, and deterministic graph analysis. Built for **Graph Hacks: Context for AI Agents (Track 1: Agents That Act on Connected Data)**.

---

## 1. Project Overview

GraphGuard investigates financial fraud concealed across networks of accounts, shared devices, and multi-hop transfers. Instead of relying on an LLM to hallucinate connections or generate unstable Cypher queries, GraphGuard executes parameterized Cypher queries and graph algorithms over FalkorDB to isolate fraud rings and safely execute reversible containment actions.

### The "FalkorDB Removal" Test
* **Why Graph?** Detecting time-respecting cyclic transfers (`A -> B -> C -> D -> A`) and shared infrastructure across arbitrary hop depths requires slow, resource-heavy recursive CTEs in relational databases.
* **Core Dependency:** FalkorDB executes multi-hop traversals and circular pattern matching in milliseconds. The application's core logic, deterministic scoring, and validation routing cannot function on relational or vector databases.

---

## 2. Key Differentiators

* **Deterministic Tooling over Free-form Cypher:** The LangGraph agent coordinates workflow state, but all graph traversals and cycle detections run via parameterized, pre-tested Cypher functions in Python.
* **Planted Decoys & Restraint:** Demonstrates precision by identifying fraud rings (`A-104`) while intentionally leaving benign look-alikes alone (`D-201`: household device sharing) using counterfactual graph checks.
* **Closed-Loop Safe Autonomy:** Features a dry-run preview, a policy-gated execution engine, automated post-mutation verification, and an instant graph-native rollback mechanism.
* **Strict Grounding:** System prompts and Pydantic models enforce that the LLM only reasons over evidence strictly pulled from FalkorDB.

---

## 3. Graph Data Model

The graph models money transfers as direct, attributed edges to optimize path traversals and cycle calculations.

```text
(:Alert) -[:ABOUT]-> (:Account) -[:USES_DEVICE]-> (:Device)
                         |      -[:USED_IP]-> (:IPAddress)
                         |
             [:SENT_MONEY {amount, ts}]
                         |
                         v
                    (:Account)
```

### Nodes
* **`Account`**: `id`, `status` (`ACTIVE`, `UNDER_REVIEW`, `HOLD`), `tier`
* **`Device`**: `id`, `fingerprint_hash`
* **`IPAddress`**: `id`, `region`, `is_shared_hub`
* **`Alert`**: `id`, `priority`, `status`
* **`AuditEvent`**: `id`, `ts`, `actor`, `action`, `prev_state`, `new_state`, `idempotency_key`

### Relationships
* **`(:Account)-[:USES_DEVICE]->(:Device)`**: Shared device clustering.
* **`(:Account)-[:USED_IP]->(:IPAddress)`**: Network association.
* **`(:Account)-[:SENT_MONEY {amount, ts}]->(:Account)`**: Directed, timestamped fund transfers.
* **`(:AuditEvent)-[:TARGETED]->(:Account)`**: Action history for instantaneous rollback.

---

## 4. Key Cypher Queries

### A. Time-Respecting Circular Flow Detection (3 to 6 Hops)
```cypher
MATCH p = (a:Account {id: $entity_id})-[:SENT_MONEY*3..6]->(a)
RETURN [n IN nodes(p) | n.id] AS cycle_nodes,
       [r IN relationships(p) | r.amount] AS amounts,
       [r IN relationships(p) | r.ts] AS timestamps
```
*Identifies money-laundering loops where funds circulate back to the origin.*

### B. Shared Infrastructure (Non-Hub Devices)
```cypher
MATCH (a:Account {id: $entity_id})-[:USES_DEVICE]->(d:Device)<-[:USES_DEVICE]-(other:Account)
WHERE other.id <> a.id
RETURN d.id AS device_id, collect(DISTINCT other.id) AS connected_accounts
```
*Detects account clusters operating from the same hardware while pruning high-degree hubs.*

### C. State Mutation & Audit Trail
```cypher
MATCH (a:Account {id: $entity_id})
SET a.status = $new_status
CREATE (ev:AuditEvent { id: $audit_id, action: $action_type, prev_state: $prev_status })
CREATE (ev)-[:TARGETED]->(a)
```
*Safely updates account statuses while maintaining a cryptographic chain of custody for rollbacks.*

---

## 5. Performance Benchmark: Graph vs. SQL

To prove the necessity of a graph database, a benchmark ([benchmark/run.py](benchmark/run.py)) measures the latency of the multi-hop cycle query finding 5-hop loops in our dataset:

* **FalkorDB (Graph Native):** ~1–2 ms (p50: 1.03 ms, p95: 1.58 ms)
* **Relational Equivalent:** Traversing 3 to 6 hops tracking origin, amounts, and path constraints using recursive SQL CTEs typically degrades to >1000 ms or triggers out-of-memory limits at scale, blocking real-time autonomous agent workflows.

---

## 6. Project Architecture

* **`apps/graph_tools/`**: Pydantic schemas and deterministic parameterized Cypher execution functions.
* **`apps/policy/`**: Hard-coded risk scoring engine (Cycle: `+40`, Device Cluster: `+25`, Decoy Mitigator: `-15`).
* **`apps/agent/`**: LangGraph state machine orchestrating the investigation path and generating dry-run JSON diffs.
* **`apps/actions/`**: Execution loop for safe graph mutations and rollback handling.
* **`apps/api/`**: FastAPI endpoints serving the agent and action backend.
* **`apps/web/`**: Streamlit interface to manage alerts, approve actions, and execute rollbacks.

---

## 7. Quickstart / Local Setup

### Prerequisites
* Docker & Docker Compose
* Python 3.11+
* Git

### Step-by-Step Instructions

1. **Clone the repository:**
   ```bash
   git clone https://github.com/nak-sh/graphguard.git
   cd graphguard
   ```

2. **Start FalkorDB:**
   ```bash
   docker compose up -d
   ```
   *FalkorDB Browser is accessible at [http://localhost:3000](http://localhost:3000).*

3. **Set up Python environment:**
   ```bash
   python -m venv venv
   # Windows:
   .\venv\Scripts\activate
   # Linux/macOS:
   source venv/bin/activate

   pip install -r requirements.txt
   ```

4. **Seed the graph & run benchmarks:**
   ```bash
   python data/generate_demo.py
   python benchmark/run.py
   ```

5. **Start the Application Stack (Run in two separate terminals):**

   **Terminal 1 (Backend API):**
   ```bash
   uvicorn apps.api.main:app --reload
   ```

   **Terminal 2 (Frontend UI):**
   ```bash
   streamlit run apps/web/app.py
   ```