# GraphGuard implementation decisions

This log records implementation choices made while bringing the supplied prototype to the v2 specification. It separates decisions from assumptions and keeps unverified database behavior out of product claims.

## D-001 — Preserve FalkorDB as the source of truth

**Decision:** All relationship traversal, cycle detection, shared infrastructure, incidents, evidence, audit events, action state, and post-action verification remain backed by FalkorDB. SQLite is allowed only as a benchmark comparator and LangGraph checkpoint store; it must not replace graph state.

**Reason:** This is the central product requirement and the graph-necessity proof for Track 1.

## D-002 — Keep the existing Python package boundary during the backend rewrite

**Decision:** Preserve the existing `apps/` package as the compatibility shell while adding explicit modules for contracts, graph access, policy, actions, gateway, agent, and MCP. Refactoring into the v2 conceptual layout will be incremental rather than a risky one-shot rename.

**Reason:** The prototype has useful imports and tests. Keeping the boundary reduces breakage while the contracts become stricter.

## D-003 — Make configuration environment-driven

**Decision:** FalkorDB host, port, graph name, API URL, gateway URL, LLM provider/model, and optional API keys are read from environment variables with documented local defaults. Secrets are never written to the repository.

**Reason:** The current hard-coded localhost values prevent Compose, CI, and non-local demos from sharing the same code path.

## D-004 — Treat temporal cycles as rotation-invariant

**Decision:** A directed cycle is time-respecting when its timestamps have at most one descent around the circular sequence. The implementation will evaluate every rotation equivalently, use a configurable `max(ts) - min(ts)` window, and never reverse the graph path or edge order.

**Reason:** Investigation may begin at any member of the ring. A cycle must not become valid merely because the traversal happens to be reversed, and a ring with one wrap at the cycle boundary must still be recognized.

**Verification status:** The pure algorithm and FalkorDB fixture tests are part of M0/M2; FalkorDB query syntax remains unverified until `docs/VERIFIED_SYNTAX.md` is produced.

## D-005 — Keep scoring and policy deterministic

**Decision:** Scoring, policy tiers, affected-account selection, dry-run diffs, approval requirements, cooldowns, caps, and verification are deterministic Python code driven by a versioned YAML policy. The LLM cannot create arbitrary actions or alter scores.

**Reason:** Safety and auditability require the same evidence and policy to produce the same decision offline.

## D-006 — Evidence is immutable input to scoring

**Decision:** The investigate phase normalizes each tool result into a stable `EvidenceItem`, persists it to an `Evidence` node, and passes that stored evidence bundle into the scorer. The scorer never re-queries to obtain a different evidence set.

**Reason:** The audited evidence must be exactly what was scored and narrated.

## D-007 — Offline-first provider abstraction

**Decision:** Provider selection supports `none` (deterministic playbook), Anthropic, and OpenAI-compatible structured tool choice. With no key or failed network call, the workflow uses the fixed read-only playbook and still completes a full demo.

**Reason:** Judges must be able to run the project without credentials or network access.

## D-008 — Safe mutation protocol

**Decision:** The action service always follows: stored incident proposal → server policy check → dry-run → approval/autonomy check → idempotent mock-gateway request → FalkorDB mutation → graph/gateway verification → tamper-evident audit event. Rollback is a compensating action, not an unguarded overwrite.

**Reason:** A client request is not authority. The server must enforce the policy and protect the rollback chain.

## D-009 — Synthetic data is explicit and bounded

**Decision:** Seed generation uses a fixed seed, named T1–T3/D1–D4 fixtures, deterministic background noise, and ground-truth labels stored outside the graph for evaluation. The UI and reports always display a synthetic-data badge and “lead, not proof” language.

**Reason:** Reproducibility and honest interpretation are required by the specification.

## D-010 — Benchmark claims are generated, not handwritten

**Decision:** Benchmark code writes machine-readable results containing dataset size, depth, query, FalkorDB version, SQL engine, warm-up count, measured iterations, p50 and p95. README benchmark tables are generated from those artifacts and remain “not measured” until the command has run.

**Reason:** The current README contains unsupported latency and SQL claims; no such claim may survive the rewrite.

## D-011 — Frontend replacement is a real application

**Decision:** The legacy prototype screen is replaced with a Next.js App Router application. It consumes typed API contracts, uses SSE for progress, and keeps graph rendering and action controls connected to the real backend rather than mock-only UI state.

**Reason:** The requested product experience is an interactive investigation workspace, not a decorated form.

## D-013 — Expose the active policy as a read-only UI contract

**Decision:** Add `GET /api/policy/current`, returning the loaded versioned policy without allowing the frontend to mutate it. The policy page uses this response to initialize sandbox controls instead of duplicating weights and thresholds in TypeScript.

**Reason:** The frontend needs honest, data-driven policy controls. A read-only endpoint avoids silently drifting from `policy.yaml` while preserving the backend as the source of truth.

## D-014 — Normalize persisted evidence at the policy API boundary

**Decision:** `/api/policy/sandbox` strips FalkorDB persistence metadata (`created_at` and `data_json`) before validating evidence against the strict shared `EvidenceItem` contract.

**Reason:** The policy sandbox must score the same cached evidence that was persisted by an incident. Storage metadata is not part of the scoring contract and previously caused valid cached evidence to be rejected as extra fields.

## D-015 — Bake the Compose API origin into the Next.js rewrite

**Decision:** The web image accepts a pinned `GRAPHGUARD_API_URL` build argument, and Compose passes `http://api:8000`. Local development retains the localhost default.

**Reason:** Next.js rewrites are evaluated during the production build. A runtime-only container environment left the shipped web image proxying to its own localhost instead of the API service.

## D-012 — Optional features are sequenced behind the safe core

**Decision:** Tier 1 signature features (containment optimizer, time-travel replay, red-team lab, tamper-evident audit verification) are implemented only after the backend action/evidence invariants and tests pass. Tier 2/3 work cannot weaken those invariants.

**Reason:** Correctness and judge-verifiable safety outrank surface area.

## Open risks and explicit non-decisions

- The exact pinned FalkorDB tag is not chosen until the M0 Docker spike proves the required Cypher and client result shapes.
- Built-in FalkorDB algorithms will not be used merely because they are listed in the concept document; each procedure must pass the spike or be replaced with a parameterized query.
- Claude is the documented preferred provider in the concept, but no provider is assumed available locally. Provider credentials are not requested or stored.
- The benchmark will report SQL competitiveness honestly; it will not be forced to show a graph win.
- A shared device, IP, or graph path is evidence/lead, not proof of fraud. No UI wording may imply adjudication.
