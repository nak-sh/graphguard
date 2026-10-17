# GraphGuard: Graph-Augmented Fraud Investigation & Safe Response Agent

> Autonomous, evidence-grounded fraud investigation agent powered by FalkorDB, LangGraph, and deterministic graph analysis. Built for **Graph Hacks: Context for AI Agents (Track 1: Agents That Act on Connected Data)**.

---

## 1. Project Overview

GraphGuard investigates financial fraud concealed across networks of accounts, shared devices, and multi-hop transfers. Instead of relying on an LLM to hallucinate connections or generate unstable Cypher queries, GraphGuard executes parameterized Cypher queries and graph algorithms over FalkorDB to isolate fraud rings and safely execute reversible containment actions.

### The "FalkorDB Removal" Test
* **Why Graph?** Detecting time-respecting cyclic transfers (`A -> B -> C -> D -> A`) and shared infrastructure across arbitrary hop depths requires slow, resource-heavy recursive CTEs in relational databases.
* **Core Dependency:** FalkorDB executes multi-hop traversals and circular pattern matching in milliseconds. The application's core logic cannot function on relational or vector databases.

---

## 2. Key Differentiators

* **Deterministic Tooling over Free-form Cypher:** The LLM coordinates workflow state and explains findings, but all graph traversals and cycle detections run via parameterized, pre-tested Cypher functions.
* **Planted Decoys & Restraint:** Demonstrates precision by identifying fraud rings (T1) while intentionally leaving benign look-alikes alone (D1: household device sharing) using counterfactual checks.
* **Closed-Loop Safe Autonomy:** Features a dry-run preview, policy gate, mock payment gateway execution with idempotency keys, re-query verification, and an instant rollback mechanism.
* **Strict Grounding:** An automated verification check blocks any LLM narrative referencing entity IDs, amounts, or paths not present in the FalkorDB evidence bundle.

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
* **`Incident`**: `id`, `status`, `summary`, `score`, `policy_version`
* **`Evidence`**: `id`, `kind`, `query_name`, `params`, `result_hash`
* **`AuditEvent`**: `id`, `ts`, `actor`, `action`, `prev_state`, `new_state`, `idempotency_key`

### Relationships
* **`(:Account)-[:USES_DEVICE]->(:Device)`**: Shared device clustering.
* **`(:Account)-[:USED_IP]->(:IPAddress)`**: Network association.
* **`(:Account)-[:SENT_MONEY {id, amount, ts}]->(:Account)`**: Directed, timestamped fund transfers.
* **`(:Alert)-[:ABOUT]->(:Account)`**: Initial trigger binding.
* **`(:Incident)-[:INVOLVES]->(:Account)`**: Affected entity tracking.
* **`(:Incident)-[:SUPPORTED_BY]->(:Evidence)`**: Audit and provenance link.
* **`(:Incident)-[:HAS_ACTION]->(:AuditEvent)`**: Action history for rollback.

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

### C. Bounded Neighborhood Traversal
```cypher
MATCH (a:Account {id: $entity_id})
OPTIONAL MATCH p = (a)-[r*1..$max_hops]-(m)
RETURN p
LIMIT $limit
```
*Extracts local subgraphs up to configurable hops for UI visualization and contextual analysis.*

---

## 5. Progress to Date

- [x] **Phase 1: Environment & Cypher Spike**
- [x] **Phase 2: Deterministic Tools & Scorer**
- [ ] **Phase 3: LangGraph Agent & Policy Engine**
- [ ] **Phase 4: Action Engine, Verification & Rollback**
- [ ] **Phase 5: Web UI & Subgraph Visualizer**
- [ ] **Phase 6: Benchmark & Submission Wrap-up**

### Completed in Phase 1
* **Container Infrastructure:** FalkorDB container running with exposed database (`6379`) and browser visualizer (`3000`) ports.
* **Synthetic Data Generation (`data/generate_demo.py`):**
  * Seeded Scenario T1: 5-node time-ordered circular laundering ring (`A-104` through `A-108`) linked to a shared device (`DEV-999`).
  * Seeded Scenario D1: 2-node family decoy (`D-201`, `D-202`) with bilateral transfers that must not trigger a multi-hop alert.
  * Configured graph schema indexes on `Account.id` and `Device.id`.
* **Spike Verification (`tests/test_cypher_spike.py`):**
  * Confirmed that `A-104` detects the 5-node cycle and returns 4 connected accounts.
  * Confirmed that `D-201` ignores 2-hop bilateral transfers (0 cycles detected), verifying restraint.
  * Verified 13 total nodes and 18 relationships in the FalkorDB Browser.

### Completed in Phase 2
* **Pydantic Tool Contracts (`apps/graph_tools/models.py`):** Established strict data contracts (`SubgraphResult`, `SharedInfraResult`, `CycleResult`, `EvidenceItem`) to decouple database results from consumption layers.
* **Deterministic Tool Layer (`apps/graph_tools/tools.py`):**
  * `get_neighborhood`: Parameterized bounded traversal returning typed node and edge models.
  * `find_shared_infrastructure`: Device/IP hardware grouping with hub-node cutoffs to suppress noisy false positives.
  * `detect_transfer_cycles`: Parameterized multi-hop cycle traversal with bidirectional timestamp validation to handle engine traversal unrolling.
* **Weighted Scoring Engine (`apps/policy/scorer.py`):**
  * Implemented versioned risk weights: Time-ordered cycle (`+40`), Shared device cluster (`+25`), Household mitigator (`-15`).
  * Policy tier thresholds: `AUTO_HOLD` ($\ge 70$), `MANUAL_REVIEW` ($40$–$69$), `NO_ACTION` ($< 40$).
* **Phase 2 Verification (`tests/test_phase2.py`):**
  * `A-104` flagged as high risk (Score: 65, Tier: `MANUAL_REVIEW`) on combined cycle and device cluster signals.
  * `D-201` safely classified as benign (Score: 0, Tier: `NO_ACTION`) via the household decoy mitigator rule.

---

## 6. Quickstart / Local Setup

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

4. **Seed the graph:**
   ```bash
   python data/generate_demo.py
   ```

5. **Run test verifications:**
   ```bash
   # Phase 1 verification
   python tests/test_cypher_spike.py

   # Phase 2 verification
   python -m tests.test_phase2
   ```

---

## 7. Next Milestones (Phase 3 & 4)

* **LangGraph Agent Workflow (`apps/agent/graph.py`):** State machine managing tool execution, dry-run diffing, and offline fallback execution.
* **Action Engine & Rollback (`apps/actions/engine.py`):** Safe execution against mock payment gateways with idempotency keys and state rollback mechanism.
* **Strict Grounding Verifier:** Automated verification preventing hallucinated entities or unsupported containment actions.

---

## 8. AI Assistant Disclosure

In compliance with Rule 11 of the hackathon guidelines:

* AI assistants (Gemini, Claude) were utilized for architectural drafting, boilerplate generation, and reviewing Cypher query syntax.
* All graph schemas, Cypher logic, deterministic scoring rules, and application code are reviewed, executed, and verified by the development team.