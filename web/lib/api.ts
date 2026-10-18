export type AutonomyMode = "OBSERVE" | "RECOMMEND" | "APPROVE" | "AUTO_WITHIN_LIMITS";

export type Alert = {
  id: string;
  priority: number | string;
  status: string;
  entity_id: string;
  created_at?: number | string;
  reason?: string;
  title?: string;
  [key: string]: unknown;
};

export type ProposedAction = {
  action_id: string;
  type: string;
  target_entity: string;
  tier?: string;
  target_status?: string;
  reason?: string;
  [key: string]: unknown;
};

export type EvidenceItem = {
  id: string;
  kind: string;
  query_name: string;
  summary: string;
  data: Record<string, unknown>;
  flagged: boolean;
  result_hash?: string | null;
  [key: string]: unknown;
};

export type InvestigationState = {
  alert_id: string;
  entity_id: string;
  step_budget: number;
  visited_tools: string[];
  evidence_items: EvidenceItem[];
  signals: Signal[];
  score: number;
  tier: string;
  findings: string[];
  proposed_actions: ProposedAction[];
  dry_run_diff: DryRunDiff | null;
  approval_status: string;
  audit_events: string[];
  policy_version: string;
  autonomy_mode: AutonomyMode;
  next_tool: string | null;
  tool_calls: number;
  incident_id: string | null;
  narrative: string;
  grounding: GroundingResult | Record<string, unknown>;
  progress: InvestigationProgress[];
  error: string | null;
  pause_for_approval: boolean;
};

export type Incident = {
  id: string;
  alert_id?: string;
  entity_id?: string;
  score?: number;
  tier?: string;
  status?: string;
  summary?: string;
  policy_version?: string;
  approval_status?: string;
  proposed_actions?: ProposedAction[];
  evidence_ids?: string[];
  evidence?: EvidenceItem[];
  dry_run_diff?: DryRunDiff | Record<string, unknown> | null;
  dry_run_completed?: boolean;
  created_at?: number | string;
  [key: string]: unknown;
};

export type Signal = {
  name?: string;
  rule?: string;
  weight?: number;
  score?: number;
  description?: string;
  [key: string]: unknown;
};

export type GroundingResult = {
  grounded: boolean;
  violations: string[];
  allowed_ids?: string[];
  allowed_amounts?: number[];
};

export type InvestigationProgress = {
  event?: string;
  ts?: number;
  tool?: string;
  reason?: string;
  duration_ms?: number;
  result_count?: number;
  score?: number;
  tier?: string;
  action_count?: number;
  approval_status?: string;
  incident_id?: string;
  message?: string;
  [key: string]: unknown;
};

export type NeighborhoodNode = { id: string; label: string; properties: Record<string, unknown> };
export type NeighborhoodEdge = { source: string; target: string; relationship: string; properties: Record<string, unknown> };
export type Neighborhood = {
  entity_id: string;
  max_hops: number;
  hub_cutoff: number;
  nodes: NeighborhoodNode[];
  edges: NeighborhoodEdge[];
  truncated: boolean;
  hub_nodes: string[];
};

export type DryRunDiffItem = {
  entity_id: string;
  node_label?: string;
  previous_state: Record<string, unknown>;
  proposed_state: Record<string, unknown>;
  changes: Record<string, { from: unknown; to: unknown }>;
  policy_tier?: string;
};

export type DryRunDiff = {
  actions?: DryRunDiffItem[];
  policy_tier?: string;
  writes?: boolean;
  entity_id?: string;
  node_label?: string;
  previous_state?: Record<string, unknown>;
  proposed_state?: Record<string, unknown>;
  changes?: Record<string, { from: unknown; to: unknown }>;
};

export type DryRunResponse = {
  success: boolean;
  dry_run?: boolean;
  entity_id?: string;
  diff?: DryRunDiffItem;
  dry_run_diff?: DryRunDiffItem;
  previous_state?: Record<string, unknown>;
  proposed_state?: Record<string, unknown>;
  error?: string;
  [key: string]: unknown;
};

export type ActionResult = {
  success: boolean;
  idempotent?: boolean;
  entity_id?: string;
  audit_id?: string;
  verified_status?: string;
  pre_state?: Record<string, unknown>;
  idempotency_key?: string;
  event_hash?: string;
  gateway?: Record<string, unknown>;
  error?: string;
  [key: string]: unknown;
};

export type AuditEvent = {
  id: string;
  chain_index?: number;
  ts?: number | string;
  actor?: string;
  action?: string;
  entity_id?: string;
  prev_state?: string | Record<string, unknown>;
  new_state?: string | Record<string, unknown>;
  idempotency_key?: string;
  prev_hash?: string;
  event_hash?: string;
  [key: string]: unknown;
};

export type ReplayEdge = {
  index: number;
  source: string;
  target: string;
  amount?: number;
  ts?: number;
  cumulative_volume: number;
  cycle_closed: boolean;
  [key: string]: unknown;
};

export type ReplayResult = {
  entity_id: string;
  edges: ReplayEdge[];
  cumulative_volume: number;
  cycle_close_index: number | null;
  cycle_closed_at: number | null;
};

export type ContainmentOption = {
  accounts: string[];
  account_count: number;
  suspicious_volume_interrupted_estimate: number;
  legitimate_volume_frozen_estimate: number;
};

export type ContainmentResult = {
  synthetic_estimates: boolean;
  method: string;
  hold_all: ContainmentOption;
  hold_optimizer_pick: ContainmentOption;
  flag_only: ContainmentOption;
  detected_cycle_count: number;
  path_edge_count: number;
};

export type RedTeamVariant = {
  variant_id: string;
  description: string;
  suggested_policy_knob?: string;
  caught?: boolean;
  tier?: string;
  score?: number;
  signals?: string[];
  scratch_graph?: string;
  executed?: boolean;
  error?: string;
};

export type RedTeamMatrix = {
  isolated_scratch_graphs: string[] | number;
  variants: RedTeamVariant[];
  honest_misses: string[];
  execution_status: string;
};

export type BenchmarkResult = {
  size: number;
  depth: number;
  query?: string;
  falkordb?: { p50_ms?: number; p95_ms?: number };
  sqlite_recursive_cte?: { p50_ms?: number; p95_ms?: number };
  [key: string]: unknown;
};

export type BenchmarkArtifact = {
  iterations: number;
  warmups: number;
  methodology: string;
  schema_version?: string;
  seed?: number;
  results: BenchmarkResult[];
};

export type PolicyModel = {
  version: string;
  thresholds: Record<string, number>;
  signals: Record<string, { weight?: number; [key: string]: unknown }>;
  parameters?: Record<string, unknown>;
};

export type PolicySandboxRow = {
  incident_id: string;
  entity_id?: string;
  original_tier?: string;
  sandbox_score?: number;
  sandbox_tier?: string;
  regression?: boolean;
  decoy_regression?: boolean;
  error?: string;
};

export type PolicySandboxResult = {
  policy: PolicyModel;
  rows: PolicySandboxRow[];
  decoy_regressions: PolicySandboxRow[];
  cached_evidence_only: boolean;
};

export type Health = { ok: boolean; falkordb?: boolean; synthetic_data?: boolean; error?: string };
export type CopilotResult = { blocked: boolean; answer: string | null; citations?: string[]; grounding?: GroundingResult; offline_mode?: boolean; violations?: string[] };
export type WhyResult = { incident: Incident; evidence: Array<EvidenceItem & { cypher_template?: string; parameters?: Record<string, unknown> }>; grounding: GroundingResult };
export type GatewayRequest = { ts?: number | string; operation?: string; entity_id?: string; idempotency_key?: string; incident_id?: string; metadata?: Record<string, unknown>; replayed?: boolean; result?: Record<string, unknown> };

const API_BASE = (process.env.NEXT_PUBLIC_API_BASE_URL || "/backend").replace(/\/$/, "");

export class ApiError extends Error {
  status: number;
  constructor(message: string, status: number) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE}${path}`, { ...init, headers: { "Content-Type": "application/json", ...(init?.headers || {}) }, cache: "no-store" });
  } catch (error) {
    throw new ApiError(error instanceof Error ? error.message : "API is unreachable", 0);
  }
  if (!response.ok) {
    let detail = response.statusText || "Request failed";
    try {
      const body = (await response.json()) as { detail?: string; error?: string };
      detail = body.detail || body.error || detail;
    } catch { /* keep status text */ }
    throw new ApiError(detail, response.status);
  }
  return (await response.json()) as T;
}

export const getHealth = () => request<Health>("/health");
export const getAlerts = (status?: string) => request<Alert[]>(`/api/alerts${status ? `?status=${encodeURIComponent(status)}` : ""}`);
export const getAlert = (alertId: string) => request<Alert>(`/api/alerts/${encodeURIComponent(alertId)}`);
function parseJsonField<T>(value: unknown, fallback: T): T {
  if (typeof value !== "string") return (value as T) ?? fallback;
  try { return JSON.parse(value) as T; } catch { return fallback; }
}
export async function getIncidents(): Promise<Incident[]> {
  const rows = await request<Array<Record<string, unknown>>>("/api/incidents");
  return rows.map((row) => ({ ...row, proposed_actions: parseJsonField<ProposedAction[]>(row.proposed_actions_json, []), dry_run_diff: parseJsonField<DryRunDiff | null>(row.dry_run_diff_json, null), evidence_ids: parseJsonField<string[]>(row.evidence_ids_json, []) })) as Incident[];
}
export const getIncident = (incidentId: string) => request<Incident>(`/api/incidents/${encodeURIComponent(incidentId)}`);
export const getIncidentEvidence = (incidentId: string) => request<EvidenceItem[]>(`/api/incidents/${encodeURIComponent(incidentId)}/evidence`);
export const getIncidentWhy = (incidentId: string) => request<WhyResult>(`/api/incidents/${encodeURIComponent(incidentId)}/why`);

export function investigate(input: { alert_id: string; entity_id: string; pause_for_approval?: boolean; autonomy_mode?: AutonomyMode; thread_id?: string }) {
  return request<InvestigationState>("/api/investigate", { method: "POST", body: JSON.stringify(input) });
}

export const getAutonomy = () => request<{ mode: AutonomyMode }>("/api/settings/autonomy");
export const setAutonomy = (mode: AutonomyMode) => request<{ mode: AutonomyMode }>("/api/settings/autonomy", { method: "PUT", body: JSON.stringify({ mode }) });

export const dryRunAction = (incident_id: string, proposed_action_id: string) => request<DryRunResponse>("/api/actions/dry-run", { method: "POST", body: JSON.stringify({ incident_id, proposed_action_id }) });
export const approveIncident = (incident_id: string, approved: boolean, actor = "analyst") => request<{ success: boolean; incident_id: string; approval_status: string; incident: Incident }>(`/api/incidents/${encodeURIComponent(incident_id)}/approval`, { method: "POST", body: JSON.stringify({ approved, actor }) });
export const executeAction = (input: { incident_id: string; proposed_action_id: string; target_entity: string; type: string; idempotency_key?: string; actor?: string }) => request<ActionResult>("/api/actions/execute", { method: "POST", body: JSON.stringify(input) });
export const rollbackAction = (audit_id: string, actor = "analyst") => request<ActionResult>("/api/actions/rollback", { method: "POST", body: JSON.stringify({ audit_id, actor }) });

export const getAudit = () => request<AuditEvent[]>("/api/audit");
export const verifyAudit = () => request<{ valid: boolean }>("/api/audit/verify");
export const simulateTampering = (auditId: string, field = "new_state") => request<{ success: boolean; audit_id: string; valid_after: boolean }>(`/api/audit/simulate-tampering?audit_id=${encodeURIComponent(auditId)}&field=${encodeURIComponent(field)}`, { method: "POST" });
export const getGatewayRequests = () => request<GatewayRequest[]>("/api/gateway/requests");

export const getNeighborhood = (entityId: string, maxHops = 4, limit = 300) => request<Neighborhood>(`/api/entities/${encodeURIComponent(entityId)}/neighborhood?max_hops=${maxHops}&limit=${limit}`);
export const getReplay = (entityId: string) => request<ReplayResult>(`/api/entities/${encodeURIComponent(entityId)}/replay`);
export const getContainment = (entityId: string) => request<ContainmentResult>(`/api/entities/${encodeURIComponent(entityId)}/containment`);
export const getRedTeamMatrix = () => request<RedTeamMatrix>("/api/red-team/matrix");
export const getBenchmark = () => request<BenchmarkArtifact>("/api/benchmark/latest");

export const getPolicyCurrent = () => request<PolicyModel>("/api/policy/current");
export const runPolicySandbox = (input: { version?: string; thresholds: Record<string, number>; weights: Record<string, number>; incident_ids?: string[] }) => request<PolicySandboxResult>("/api/policy/sandbox", { method: "POST", body: JSON.stringify(input) });
export const savePolicySandbox = (input: { version: string; thresholds: Record<string, number>; weights: Record<string, number>; incident_ids?: string[] }) => request<{ saved: boolean; version: string; path: string }>("/api/policy/sandbox/save", { method: "POST", body: JSON.stringify(input) });
export const copilot = (incident_id: string, question: string) => request<CopilotResult>("/api/copilot", { method: "POST", body: JSON.stringify({ incident_id, question }) });

export type InvestigationEvent = InvestigationProgress & { state?: InvestigationState; error?: string };

export async function streamInvestigation(input: { alert_id: string; entity_id: string; thread_id?: string }, onEvent: (event: InvestigationEvent) => void, signal?: AbortSignal): Promise<void> {
  const query = new URLSearchParams({ alert_id: input.alert_id, entity_id: input.entity_id });
  if (input.thread_id) query.set("thread_id", input.thread_id);
  let response: Response;
  try {
    response = await fetch(`${API_BASE}/api/investigate/stream?${query.toString()}`, { headers: { Accept: "text/event-stream" }, cache: "no-store", signal });
  } catch (error) {
    throw new ApiError(error instanceof Error ? error.message : "Investigation stream unavailable", 0);
  }
  if (!response.ok || !response.body) throw new ApiError("Investigation stream unavailable", response.status || 503);
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const records = buffer.split("\n\n");
    buffer = records.pop() || "";
    for (const record of records) {
      const data = record.split("\n").filter((line) => line.startsWith("data:")).map((line) => line.slice(5).trim()).join("\n");
      if (!data) continue;
      let parsed: InvestigationEvent;
      try { parsed = JSON.parse(data) as InvestigationEvent; } catch { onEvent({ event: "progress", message: data }); continue; }
      if (parsed.event === "error") throw new ApiError(String(parsed.error || parsed.message || "Investigation stream failed"), 502);
      onEvent(parsed);
    }
  }
}
