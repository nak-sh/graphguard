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
  reason?: string;
  [key: string]: unknown;
};

export type Incident = {
  id: string;
  alert_id?: string;
  entity_id?: string;
  risk_score?: number;
  risk_tier?: string;
  tier?: string;
  confidence?: number;
  approval_status?: string;
  proposed_actions?: ProposedAction[];
  evidence?: EvidenceItem[];
  evidence_count?: number;
  dry_run_completed?: boolean;
  dry_run_diff?: Record<string, unknown>;
  [key: string]: unknown;
};

export type EvidenceItem = {
  id: string;
  kind: string;
  query_name: string;
  summary: string;
  flagged?: boolean;
  data?: Record<string, unknown>;
  result_hash?: string;
};

export type Neighborhood = {
  entity_id: string;
  nodes: Array<{ id: string; label: string; properties?: Record<string, unknown> }>;
  edges: Array<{ source: string; target: string; relationship: string; properties?: Record<string, unknown> }>;
  hub_nodes?: string[];
  truncated?: boolean;
};

export type InvestigationEvent = {
  event?: string;
  step?: string;
  message?: string;
  incident?: Incident;
  [key: string]: unknown;
};

export type Health = { ok: boolean; falkordb?: boolean; synthetic_data?: boolean; error?: string };

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
  const response = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...(init?.headers || {}) },
    cache: "no-store",
  });
  if (!response.ok) {
    let detail = response.statusText;
    try {
      const body = (await response.json()) as { detail?: string };
      detail = body.detail || detail;
    } catch {
      // Keep the HTTP status text when the service does not return JSON.
    }
    throw new ApiError(detail, response.status);
  }
  return (await response.json()) as T;
}

export function getHealth(): Promise<Health> {
  return request<Health>("/health");
}

export function getAlerts(status?: string): Promise<Alert[]> {
  const query = status ? `?status=${encodeURIComponent(status)}` : "";
  return request<Alert[]>(`/api/alerts${query}`);
}

export function getAlert(alertId: string): Promise<Alert> {
  return request<Alert>(`/api/alerts/${encodeURIComponent(alertId)}`);
}

export function getIncident(incidentId: string): Promise<Incident> {
  return request<Incident>(`/api/incidents/${encodeURIComponent(incidentId)}`);
}

export function getIncidents(): Promise<Incident[]> {
  return request<Incident[]>("/api/incidents");
}

export function investigate(input: {
  alert_id: string;
  entity_id: string;
  pause_for_approval?: boolean;
  autonomy_mode?: AutonomyMode;
  thread_id?: string;
}): Promise<Incident> {
  return request<Incident>("/api/investigate", {
    method: "POST",
    body: JSON.stringify({ pause_for_approval: false, autonomy_mode: "APPROVE", ...input }),
  });
}

export function getAutonomy(): Promise<{ mode: AutonomyMode }> {
  return request<{ mode: AutonomyMode }>("/api/settings/autonomy");
}

export function setAutonomy(mode: AutonomyMode): Promise<{ mode: AutonomyMode }> {
  return request<{ mode: AutonomyMode }>("/api/settings/autonomy", {
    method: "PUT",
    body: JSON.stringify({ mode }),
  });
}

export function dryRunAction(incident_id: string, proposed_action_id: string): Promise<Record<string, unknown>> {
  return request<Record<string, unknown>>("/api/actions/dry-run", {
    method: "POST",
    body: JSON.stringify({ incident_id, proposed_action_id }),
  });
}

export function executeAction(input: {
  incident_id: string;
  proposed_action_id: string;
  target_entity: string;
  type: string;
  actor?: string;
}): Promise<Record<string, unknown>> {
  return request<Record<string, unknown>>("/api/actions/execute", {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export function getAudit(): Promise<Record<string, unknown>[]> {
  return request<Record<string, unknown>[]>("/api/audit");
}

export function verifyAudit(): Promise<{ valid: boolean }> {
  return request<{ valid: boolean }>("/api/audit/verify");
}

export function getNeighborhood(entityId: string): Promise<Neighborhood> {
  return request<Neighborhood>(`/api/entities/${encodeURIComponent(entityId)}/neighborhood`);
}

export function getReplay(entityId: string): Promise<{ entity_id: string; edges: Array<Record<string, unknown>>; cumulative_volume: number; cycle_close_index: number | null; cycle_closed_at: number | null }> {
  return request(`/api/entities/${encodeURIComponent(entityId)}/replay`);
}

export function getContainment(entityId: string): Promise<Record<string, unknown>> {
  return request(`/api/entities/${encodeURIComponent(entityId)}/containment`);
}

export function getRedTeamMatrix(): Promise<Record<string, unknown>> {
  return request("/api/red-team/matrix");
}

export function getBenchmark(): Promise<Record<string, unknown>> {
  return request("/api/benchmark/latest");
}

/**
 * Consume the FastAPI event stream. The caller can fall back to `investigate`
 * when a deployment or proxy does not support streaming responses.
 */
export async function streamInvestigation(
  input: { alert_id: string; entity_id: string; thread_id?: string },
  onEvent: (event: InvestigationEvent) => void,
  signal?: AbortSignal,
): Promise<void> {
  const query = new URLSearchParams({ alert_id: input.alert_id, entity_id: input.entity_id });
  if (input.thread_id) query.set("thread_id", input.thread_id);
  const response = await fetch(`${API_BASE}/api/investigate/stream?${query.toString()}`, {
    headers: { Accept: "text/event-stream" },
    cache: "no-store",
    signal,
  });
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
      const data = record
        .split("\n")
        .filter((line) => line.startsWith("data:"))
        .map((line) => line.slice(5).trim())
        .join("\n");
      if (!data) continue;
      let parsed: InvestigationEvent;
      try {
        parsed = JSON.parse(data) as InvestigationEvent;
      } catch {
        onEvent({ event: "progress", message: data });
        continue;
      }
      if (parsed.event === "error") throw new ApiError(String(parsed.error || parsed.message || "Investigation stream failed"), 502);
      onEvent(parsed);
    }
  }
}

export const fallbackAlerts: Alert[] = [
  {
    id: "ALERT-104",
    priority: 1,
    status: "OPEN",
    entity_id: "A-104",
    title: "Time-respecting transfer ring",
    reason: "Five-account synthetic cycle requires review",
    created_at: "2024-01-01T14:04:00Z",
  },
  {
    id: "ALERT-T2-201",
    priority: 2,
    status: "OPEN",
    entity_id: "T2-201",
    title: "Directed mule-chain pattern",
    reason: "Bounded path reaches a synthetic confirmed-bad anchor",
    created_at: "2024-01-01T13:52:00Z",
  },
  {
    id: "ALERT-D201",
    priority: 3,
    status: "OPEN",
    entity_id: "D-201",
    title: "Household look-alike",
    reason: "Shared family device with small mutual transfers",
    created_at: "2024-01-01T13:31:00Z",
  },
];
