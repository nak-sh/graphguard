"use client";

import { useEffect, useMemo, useRef, useState, type CSSProperties, type ReactNode } from "react";
import Link from "next/link";
import cytoscape from "cytoscape";
import fcose from "cytoscape-fcose";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Check, ChevronDown, CircleAlert, Clock3, Code2, Copy, Database, ExternalLink, FileText, Hand, LoaderCircle, MessageSquare, Play, RefreshCw, RotateCcw, Search, ShieldAlert, Undo2, X } from "lucide-react";
import {
  approveIncident, copilot, dryRunAction, executeAction, getAlerts, getAudit, getGatewayRequests, getIncident, getIncidentEvidence, getIncidents, getIncidentWhy, getNeighborhood, investigate, rollbackAction, streamInvestigation, verifyAudit,
  type Alert, type AutonomyMode, type DryRunResponse, type EvidenceItem, type Incident, type InvestigationEvent, type InvestigationState, type Neighborhood, type ProposedAction,
} from "@/lib/api";
import { useGraphGuardStore } from "@/lib/store";

type Core = any;
type ElementDefinition = any;
cytoscape.use(fcose as never);

type DrawerTab = "evidence" | "score" | "why" | "actions" | "copilot";

function Loading({ label = "Loading live result…" }: { label?: string }) { return <div className="empty-state loading-state"><LoaderCircle size={17} className="spin" /><span>{label}</span></div>; }
function EmptyState({ title, body, action }: { title: string; body: string; action?: ReactNode }) { return <div className="empty-state"><CircleAlert size={18} /><div><strong>{title}</strong><p>{body}</p>{action}</div></div>; }
function ErrorState({ message, retry }: { message: string; retry?: () => void }) { return <div className="empty-state error-state"><ShieldAlert size={18} /><div><strong>Live result unavailable</strong><p>{message}</p>{retry && <button className="button compact" onClick={retry}>Retry</button>}</div></div>; }
function apiValue(value: unknown) { return typeof value === "object" && value !== null ? JSON.stringify(value, null, 2) : String(value ?? "—"); }
function priorityNumber(value: Alert["priority"]) { const number = Number(value); return Number.isFinite(number) ? number : 3; }
function alertTitle(alert: Alert) { return alert.title || alert.reason || "Alert requires investigation"; }
function incidentFromState(state: InvestigationState): Incident | null { return state.incident_id ? { id: state.incident_id, alert_id: state.alert_id, entity_id: state.entity_id, score: state.score, tier: state.tier, approval_status: state.approval_status, proposed_actions: state.proposed_actions, dry_run_diff: state.dry_run_diff, summary: state.narrative, policy_version: state.policy_version, evidence: state.evidence_items, dry_run_completed: Boolean(state.dry_run_diff) } : null; }

function cycleMembership(evidence: EvidenceItem[]) {
  const item = evidence.find((entry) => entry.kind === "CYCLE");
  const data = item?.data || {};
  const rawNodes = data.cycle_nodes;
  const nodes = Array.isArray(rawNodes) ? rawNodes.map(String) : [];
  const edges = new Set<string>();
  nodes.forEach((node, index) => { const next = nodes[(index + 1) % nodes.length]; if (next) edges.add(`${node}→${next}`); });
  return { nodes: new Set(nodes), edges };
}

function GraphCanvas({ neighborhood, evidence, maxHops, setMaxHops, selectedEvidenceId, onEvidenceSelect }: { neighborhood: Neighborhood | undefined; evidence: EvidenceItem[]; maxHops: number; setMaxHops: (value: number) => void; selectedEvidenceId: string | null; onEvidenceSelect: (id: string | null) => void }) {
  const containerRef = useRef<HTMLDivElement>(null);
  const cyRef = useRef<Core | null>(null);
  const [pinned, setPinned] = useState<{ id: string; label: string; properties: Record<string, unknown> } | null>(null);
  const cycle = cycleMembership(evidence);
  const visibleNodes = useMemo(() => neighborhood?.nodes.slice(0, 300) || [], [neighborhood]);
  const visibleIds = new Set(visibleNodes.map((node) => node.id));
  const visibleEdges = (neighborhood?.edges || []).filter((edge) => visibleIds.has(edge.source) && visibleIds.has(edge.target));
  const hiddenCount = Math.max(0, (neighborhood?.nodes.length || 0) - visibleNodes.length);

  useEffect(() => {
    if (!containerRef.current || !neighborhood) return;
    const elements: ElementDefinition[] = visibleNodes.map((node) => ({ data: { id: node.id, label: node.label, properties: node.properties, hub: neighborhood.hub_nodes.includes(node.id), cycle: cycle.nodes.has(node.id) } }));
    visibleEdges.forEach((edge, index) => elements.push({ data: { id: `${edge.source}-${edge.target}-${index}`, source: edge.source, target: edge.target, relationship: edge.relationship, amount: Number(edge.properties.amount || 0), cycle: edge.relationship === "SENT_MONEY" && cycle.edges.has(`${edge.source}→${edge.target}`) } }));
    const cy = cytoscape({ container: containerRef.current, elements, wheelSensitivity: 0.18, minZoom: 0.2, maxZoom: 3, style: [
      { selector: "node", style: { "background-color": "#243242", "border-color": "#73869a", "border-width": 1.5, label: "data(id)", color: "#d8e2eb", "font-size": 10, "font-family": "JetBrains Mono, monospace", "text-valign": "center", "text-halign": "center", width: 38, height: 38, "text-wrap": "ellipsis", "text-max-width": 56 } },
      { selector: 'node[label="Device"]', style: { "background-color": "#17343a", "border-color": "#56d6e8", shape: "round-rectangle" } },
      { selector: 'node[label="IPAddress"]', style: { "background-color": "#282342", "border-color": "#ae9cff", shape: "diamond" } },
      { selector: 'node[properties.status = "HOLD"]', style: { "background-color": "#4d2028", "border-color": "#f07878", "border-width": 2.5 } },
      { selector: 'node[properties.status = "UNDER_REVIEW"]', style: { "background-color": "#4b3823", "border-color": "#f2b45f", "border-width": 2.5 } },
      { selector: "node[hub = true]", style: { opacity: 0.62, "border-style": "dashed", "border-color": "#f2b45f", label: "data(id)", "text-background-color": "#171c23", "text-background-opacity": 1, "text-background-padding": 2 } },
      { selector: "node[cycle = true]", style: { "border-color": "#f07878", "border-width": 3, shadow: "0 0 14px #f07878" } },
      { selector: "edge", style: { width: "mapData(amount, 0, 10000, 1, 7)", "line-color": "#506476", "target-arrow-color": "#506476", "target-arrow-shape": "triangle", "curve-style": "bezier", "line-style": "dashed", "line-dash-pattern": [5, 4], opacity: 0.85 } },
      { selector: "edge[cycle = true]", style: { "line-color": "#f07878", "target-arrow-color": "#f07878", width: 4, "line-style": "solid", opacity: 1 } },
    ], layout: { name: "fcose", animate: false, quality: "default", randomize: true, fit: true, padding: 42 } as any });
    cy.on("tap", "node", (event: any) => { const node: any = event.target; setPinned({ id: node.id(), label: node.data("label"), properties: node.data("properties") || {} }); });
    cyRef.current = cy;
    return () => { cy.destroy(); cyRef.current = null; };
  }, [neighborhood, visibleNodes, visibleEdges, cycle.edges, cycle.nodes]);

  useEffect(() => { if (selectedEvidenceId && cycle.nodes.size) cyRef.current?.nodes().forEach((node: any) => node.toggleClass("evidence-focus", cycle.nodes.has(node.id()))); }, [selectedEvidenceId, cycle.nodes]);

  if (!neighborhood) return <EmptyState title="No graph result yet" body="Run an investigation or select an alert with a reachable graph neighborhood." />;
  return <div className="graph-shell"><div className="graph-toolbar"><label>Hop depth <input type="range" min="1" max="4" value={maxHops} onChange={(event) => setMaxHops(Number(event.target.value))} /><span className="mono">{maxHops}</span></label><div className="graph-actions"><button className="icon-button" title="Fit graph" onClick={() => cyRef.current?.fit(undefined, 35)}><Search size={15} /></button><button className="icon-button" title="Zoom in" onClick={() => cyRef.current?.zoom(cyRef.current.zoom() * 1.2)}><span>+</span></button><button className="icon-button" title="Zoom out" onClick={() => cyRef.current?.zoom(cyRef.current.zoom() * 0.8)}><span>−</span></button></div></div><div className="cytoscape-canvas" ref={containerRef} aria-label="FalkorDB neighborhood graph" />{hiddenCount > 0 && <div className="graph-truncation">{hiddenCount} more nodes hidden · bounded at 300 for smooth rendering</div>}<div className="graph-legend"><span><i className="legend-swatch account" /> Account</span><span><i className="legend-swatch device" /> Device</span><span><i className="legend-swatch ip" /> IP address</span><span><i className="legend-swatch cycle" /> Detected cycle</span><span><i className="legend-swatch hub" /> Hub</span></div>{pinned && <div className="node-popover"><div className="popover-head"><strong>{pinned.id}</strong><button className="icon-button" onClick={() => setPinned(null)} aria-label="Close node details"><X size={14} /></button></div><span className="badge cyan">{pinned.label}</span><pre>{JSON.stringify(pinned.properties, null, 2)}</pre></div>}</div>;
}

function HoldButton({ disabled, onConfirm, label }: { disabled?: boolean; onConfirm: () => void; label: string }) {
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const [holding, setHolding] = useState(false);
  function start() { if (disabled) return; setHolding(true); timer.current = setTimeout(() => { setHolding(false); onConfirm(); }, 900); }
  function stop() { if (timer.current) clearTimeout(timer.current); timer.current = null; setHolding(false); }
  return <button className="button danger hold-button" disabled={disabled} onPointerDown={start} onPointerUp={stop} onPointerLeave={stop}><Hand size={14} />{holding ? "Hold…" : label}</button>;
}

function EvidenceView({ evidence, selectedEvidenceId, onSelect }: { evidence: EvidenceItem[]; selectedEvidenceId: string | null; onSelect: (id: string) => void }) {
  if (!evidence.length) return <EmptyState title="No evidence stored" body="The backend did not return an evidence bundle for this incident." />;
  return <div className="drawer-scroll">{evidence.map((item) => <details key={item.id} className={`evidence-card ${item.flagged ? "flagged" : "cleared"} ${selectedEvidenceId === item.id ? "selected" : ""}`} open={selectedEvidenceId === item.id}><summary onClick={() => onSelect(item.id)}><span className="evidence-kind">{item.kind}</span><span className="evidence-id mono">{item.id}</span><span className="evidence-status">{item.flagged ? "FLAGGED" : "CLEARED"}</span></summary><p>{item.summary}</p><div className="evidence-meta"><span>{item.query_name}</span>{item.result_hash && <span className="mono">{item.result_hash.slice(0, 12)}…</span>}</div><pre>{JSON.stringify(item.data, null, 2)}</pre></details>)}</div>;
}

function ScoreView({ incident, evidence }: { incident: Incident | null; evidence: EvidenceItem[] }) {
  if (!incident) return <EmptyState title="Score unavailable" body="Investigate this alert before viewing deterministic signals." />;
  const score = Number(incident.score ?? 0);
  const signals = evidence.flatMap((item) => { const raw = item.data.signals; return Array.isArray(raw) ? raw : []; });
  return <div className="drawer-scroll score-view"><div className="score-hero"><div className="score-ring" style={{ "--score-angle": `${Math.min(100, Math.max(0, score)) * 3.6}deg` } as CSSProperties}><strong>{score}</strong><span>/ 100</span></div><div><span className="eyebrow">Deterministic policy result</span><h3>{String(incident.tier || "NO_ACTION").replaceAll("_", " ")}</h3><p>Computed from the stored evidence bundle. Relationships are leads, not proof.</p></div></div><div className="signal-list">{signals.length ? signals.map((signal, index) => <div className="signal-row" key={`${String((signal as Record<string, unknown>).rule || (signal as Record<string, unknown>).name || "signal")}-${index}`}><span>{String((signal as Record<string, unknown>).rule || (signal as Record<string, unknown>).name || "Signal")}</span><strong>{String((signal as Record<string, unknown>).weight ?? (signal as Record<string, unknown>).score ?? 0)}</strong><small>{String((signal as Record<string, unknown>).description || "Stored policy signal")}</small></div>) : <EmptyState title="No signals returned" body="The incident has a score but no signal breakdown in its stored evidence." />}</div></div>;
}

function ActionView({ incident, autonomy, onError, onRefresh }: { incident: Incident; autonomy: AutonomyMode | null; onError: (message: string) => void; onRefresh: () => void }) {
  const queryClient = useQueryClient();
  const [dryRuns, setDryRuns] = useState<Record<string, DryRunResponse>>({});
  const [executions, setExecutions] = useState<Record<string, { audit_id?: string; verified_status?: string; idempotent?: boolean }>>({});
  const [busy, setBusy] = useState<string | null>(null);
  const [approved, setApproved] = useState(incident.approval_status === "APPROVED");
  const gatewayQuery = useQuery({ queryKey: ["gateway"], queryFn: getGatewayRequests, enabled: Object.keys(executions).length > 0 });
  const actions = incident.proposed_actions || [];
  const approvalRequired = incident.approval_status === "PENDING" && !approved;
  if (autonomy === "OBSERVE") return <EmptyState title="Observe mode" body="The backend is configured to observe only. Action proposals are intentionally withheld from the operator." />;
  if (!actions.length) return <EmptyState title="No proposed actions" body="This incident did not produce an action plan. Review the Why / Why-not tab for the deterministic explanation." />;
  async function doDryRun(action: ProposedAction) { setBusy(action.action_id); try { const result = await dryRunAction(incident.id, action.action_id); if (!result.success) throw new Error(result.error || "Dry run rejected"); setDryRuns((current) => ({ ...current, [action.action_id]: result })); onRefresh(); } catch (error) { onError(error instanceof Error ? error.message : "Dry run failed"); } finally { setBusy(null); } }
  async function approve(approvedValue: boolean) { setBusy("approval"); try { const result = await approveIncident(incident.id, approvedValue); setApproved(result.approval_status === "APPROVED"); onRefresh(); } catch (error) { onError(error instanceof Error ? error.message : "Approval failed"); } finally { setBusy(null); } }
  async function execute(action: ProposedAction) { const dryRun = dryRuns[action.action_id]; if (!dryRun?.success) { onError("A successful dry run is required before execution."); return; } if (approvalRequired) { onError("Analyst approval is required before execution."); return; } setBusy(action.action_id); try { const result = await executeAction({ incident_id: incident.id, proposed_action_id: action.action_id, target_entity: action.target_entity, type: action.type }); if (!result.success) throw new Error(result.error || "Action rejected"); setExecutions((current) => ({ ...current, [action.action_id]: result })); await queryClient.invalidateQueries({ queryKey: ["audit"] }); await queryClient.invalidateQueries({ queryKey: ["incidents"] }); await queryClient.invalidateQueries({ queryKey: ["neighborhood"] }); } catch (error) { onError(error instanceof Error ? error.message : "Action rejected"); } finally { setBusy(null); } }
  async function undo(action: ProposedAction) { const auditId = executions[action.action_id]?.audit_id; if (!auditId) return; setBusy(`undo-${action.action_id}`); try { const result = await rollbackAction(auditId); if (!result.success) throw new Error(result.error || "Rollback rejected"); setExecutions((current) => ({ ...current, [action.action_id]: { ...current[action.action_id], verified_status: result.verified_status } })); await queryClient.invalidateQueries({ queryKey: ["audit"] }); await queryClient.invalidateQueries({ queryKey: ["gateway"] }); await queryClient.invalidateQueries({ queryKey: ["neighborhood"] }); } catch (error) { onError(error instanceof Error ? error.message : "Rollback rejected"); } finally { setBusy(null); } }
  const grouped = new Map<string, ProposedAction[]>(); actions.forEach((action) => grouped.set(action.tier || "UNSPECIFIED", [...(grouped.get(action.tier || "UNSPECIFIED") || []), action]));
  return <div className="drawer-scroll action-view">{autonomy === "RECOMMEND" && <div className="notice amber"><CircleAlert size={15} /> Recommend mode: proposals and dry runs are visible, execution is disabled.</div>}{approvalRequired && <div className="notice amber"><CircleAlert size={15} /><span>Incident approval is required before execution.</span><button className="button compact" disabled={busy === "approval"} onClick={() => approve(true)}>Approve incident</button><button className="text-button" disabled={busy === "approval"} onClick={() => approve(false)}>Reject</button></div>}{Array.from(grouped.entries()).map(([tier, tierActions]) => <section className="action-group" key={tier}><div className="section-head"><div><span className="eyebrow">Policy tier</span><h3>{tier.replaceAll("_", " ")}</h3></div><span className="badge amber">{tierActions.length} action{tierActions.length === 1 ? "" : "s"}</span></div>{tierActions.map((action) => { const dryRun = dryRuns[action.action_id]; const execution = executions[action.action_id]; return <div className="action-card" key={action.action_id}><div className="action-card-head"><div><strong>{action.type.replaceAll("_", " ")}</strong><span className="mono">{action.action_id}</span></div><span className="badge cyan">{action.target_entity}</span></div>{action.reason && <p>{action.reason}</p>}<div className="action-controls"><button className="button compact" disabled={busy === action.action_id} onClick={() => doDryRun(action)}>{busy === action.action_id ? "Checking…" : dryRun?.success ? "Re-run dry run" : "Dry-run exact diff"}</button>{autonomy !== "RECOMMEND" && <HoldButton disabled={!dryRun?.success || approvalRequired || Boolean(execution) || busy === action.action_id} onConfirm={() => execute(action)} label="Hold to execute" />}{execution && <button className="button compact" onClick={() => undo(action)} disabled={busy === `undo-${action.action_id}`}><Undo2 size={14} /> {busy === `undo-${action.action_id}` ? "Undoing…" : `Undo (${execution.verified_status || "restored"})`}</button>}</div>{dryRun?.success && <div className="diff-list">{(dryRun.diff?.changes ? Object.entries(dryRun.diff.changes) : []).map(([key, change]) => <div className="diff-row" key={key}><span>{key}</span><span className="diff-from">{apiValue(change.from)}</span><span>→</span><span className="diff-to">{apiValue(change.to)}</span></div>)}</div>}{execution && <div className="verified-note"><Check size={14} /> Verified status: {execution.verified_status || "returned by backend"}{execution.idempotent ? " · idempotent replay" : ""}</div>}</div>; })}</section>) }{gatewayQuery.data && <section className="gateway-log"><div className="section-head"><div><span className="eyebrow">Mock gateway</span><h3>Request log</h3></div><span className="badge green">{gatewayQuery.data.length} requests</span></div>{gatewayQuery.data.slice(-6).map((request, index) => <div className="gateway-row" key={`${request.idempotency_key || "request"}-${index}`}><span className="mono">{request.operation}</span><span>{request.entity_id}</span><span className="mono">{request.idempotency_key || "—"}</span><span>{request.replayed ? "REPLAYED" : "APPLIED"}</span></div>)}</section>}</div>;
}

function WhyView({ incident }: { incident: Incident }) { const query = useQuery({ queryKey: ["why", incident.id], queryFn: () => getIncidentWhy(incident.id) }); if (query.isLoading) return <Loading />; if (query.isError) return <ErrorState message="The backend could not return the stored explanation." retry={() => query.refetch()} />; const data = query.data; if (!data) return null; return <div className="drawer-scroll"><div className={`grounding-badge ${data.grounding.grounded ? "valid" : "invalid"}`}><Check size={14} /> {data.grounding.grounded ? "Grounding verified" : "Grounding violations present"}</div><div className="why-copy">{incident.tier === "NO_ACTION" ? "No action was proposed. The counterfactual explanation below records which stored signals and mitigators kept this entity below an action tier." : "This explanation is tied to the incident's stored evidence and parameterized query templates."}</div>{data.evidence.map((item) => <details className="why-card" key={item.id}><summary><span className="mono">{item.id}</span><span>{item.query_name}</span></summary><pre>{item.cypher_template || "No query template returned"}{"\n\n"}{JSON.stringify(item.parameters || {}, null, 2)}</pre></details>)}</div>; }

function CopilotView({ incident, onCitation }: { incident: Incident; onCitation: (id: string) => void }) { const [question, setQuestion] = useState(""); const [answer, setAnswer] = useState<Awaited<ReturnType<typeof copilot>> | null>(null); const [busy, setBusy] = useState(false); async function ask() { if (!question.trim()) return; setBusy(true); try { setAnswer(await copilot(incident.id, question.trim())); } catch (error) { setAnswer({ blocked: true, answer: error instanceof Error ? error.message : "Copilot unavailable", violations: ["API request failed"] }); } finally { setBusy(false); } } return <div className="drawer-scroll copilot-view"><div className="notice violet"><MessageSquare size={15} /> Copilot can summarize stored evidence only. It cannot change scores or permissions.</div><textarea value={question} onChange={(event) => setQuestion(event.target.value)} placeholder="Ask about this incident…" rows={3} /><button className="button primary" disabled={busy || !question.trim()} onClick={ask}>{busy ? "Checking evidence…" : "Ask copilot"}</button>{answer && <div className="copilot-answer"><div className={`grounding-badge ${answer.blocked ? "invalid" : "valid"}`}>{answer.blocked ? "Blocked by grounding check" : answer.offline_mode ? "Offline grounded mode" : "Grounding verified"}</div><p>{answer.answer || answer.violations?.join("; ")}</p>{answer.citations?.map((id) => <button className="citation-chip" key={id} onClick={() => onCitation(id)}>{id}</button>)}</div>}</div>; }

function GuidedDemo({ alerts, autonomy, onSelect, onState }: { alerts: Alert[]; autonomy: AutonomyMode | null; onSelect: (alert: Alert) => void; onState: (state: InvestigationState) => void }) {
  const [open, setOpen] = useState(false);
  const [running, setRunning] = useState(false);
  const [steps, setSteps] = useState<Array<{ label: string; status: "running" | "done" | "failed"; detail?: string }>>([]);
  async function run() {
    const ring = alerts.find((alert) => `${alert.title || ""} ${alert.reason || ""}`.toLowerCase().includes("ring"));
    const household = alerts.find((alert) => `${alert.title || ""} ${alert.reason || ""}`.toLowerCase().match(/family|household/));
    const office = alerts.find((alert) => `${alert.title || ""} ${alert.reason || ""}`.toLowerCase().match(/office|shared ip|hub/));
    if (!ring) { setSteps([{ label: "Find ring alert in live API response", status: "failed", detail: "No live alert title or reason identified as a ring." }]); setOpen(true); return; }
    setOpen(true); setRunning(true); setSteps([]);
    let stepIndex = 0;
    const step = async (label: string, task: () => Promise<string | void>) => { const index = stepIndex++; setSteps((current) => [...current, { label, status: "running" }]); try { const detail = await task(); setSteps((current) => current.map((item, itemIndex) => itemIndex === index ? { ...item, status: "done", detail: detail ?? undefined } : item)); } catch (error) { const detail = error instanceof Error ? error.message : "Step failed"; setSteps((current) => current.map((item, itemIndex) => itemIndex === index ? { ...item, status: "failed", detail } : item)); throw error; } };
    try {
      onSelect(ring);
      let ringState: InvestigationState | null = null;
      await step(`Investigate live ring alert ${ring.id}`, async () => { ringState = await investigate({ alert_id: ring.id, entity_id: ring.entity_id, autonomy_mode: autonomy || "APPROVE" }); if (ringState) onState(ringState); return ringState ? `score ${ringState.score} · ${ringState.tier}` : "No state returned"; });
      const stateAfterRing = ringState as InvestigationState | null;
      const action = stateAfterRing?.proposed_actions?.[0];
      if (stateAfterRing?.incident_id && action) {
        await step("Dry-run the first stored action", async () => { const result = await dryRunAction(stateAfterRing.incident_id!, action.action_id); if (!result.success) throw new Error(result.error || "Dry run rejected"); return `${Object.keys(result.diff?.changes || {}).length} returned change(s)`; });
        if (stateAfterRing.approval_status === "PENDING") await step("Approve through the backend gate", async () => { const result = await approveIncident(stateAfterRing.incident_id!, true, "guided-demo"); if (result.approval_status !== "APPROVED") throw new Error(result.approval_status); return result.approval_status; });
        let auditId = "";
        await step("Execute through the safe action service", async () => { const result = await executeAction({ incident_id: stateAfterRing.incident_id!, proposed_action_id: action.action_id, target_entity: action.target_entity, type: action.type, actor: "guided-demo" }); if (!result.success) throw new Error(result.error || "Execution rejected"); auditId = result.audit_id || ""; return `${result.verified_status || "verified"}${result.idempotent ? " · replayed" : ""}`; });
        if (auditId) await step("Verify the tamper-evident chain", async () => { const result = await verifyAudit(); if (!result.valid) throw new Error("Audit chain is invalid"); return "valid"; });
        if (auditId) await step("Undo and verify restored state", async () => { const result = await rollbackAction(auditId, "guided-demo"); if (!result.success) throw new Error(result.error || "Rollback rejected"); return result.verified_status || "restored"; });
      } else await step("Action loop", async () => "No stored action returned for the live ring incident");
      for (const decoy of [household, office].filter((value): value is Alert => Boolean(value))) await step(`Investigate decoy ${decoy.id}`, async () => { const state = await investigate({ alert_id: decoy.id, entity_id: decoy.entity_id, autonomy_mode: autonomy || "APPROVE" }); onSelect(decoy); onState(state); return `score ${state.score} · ${state.tier} · ${state.proposed_actions.length} action(s)`; });
    } catch { /* the failed step is visible in the modal */ } finally { setRunning(false); }
  }
  return <><button className="button" disabled={!alerts.length || running} onClick={run}><Play size={14} />{running ? "Running guided demo…" : "Run guided demo"}</button>{open && <div className="demo-modal-backdrop"><div className="demo-modal" role="dialog" aria-modal="true" aria-labelledby="guided-demo-title"><div className="section-head"><div><span className="eyebrow">Guided demo / live API</span><h2 id="guided-demo-title">Safe response walkthrough</h2></div><button className="icon-button" onClick={() => setOpen(false)} aria-label="Close guided demo"><X size={15} /></button></div><p className="module-note">This walkthrough calls the current backend. It does not play recorded results and it respects the selected autonomy mode.</p><div className="demo-steps">{steps.map((stepItem, index) => <div className={`demo-step ${stepItem.status}`} key={`${stepItem.label}-${index}`}><span>{stepItem.status === "done" ? <Check size={14} /> : stepItem.status === "failed" ? <X size={14} /> : <LoaderCircle size={14} className="spin" />}</span><div><strong>{stepItem.label}</strong>{stepItem.detail && <small>{stepItem.detail}</small>}</div></div>)}</div>{!running && <button className="button primary" onClick={run}>Run again</button>}</div></div>}</>;
}

export default function MissionControl() {
  const queryClient = useQueryClient();
  const selectedAlertId = useGraphGuardStore((state) => state.selectedAlertId);
  const selectedEntityId = useGraphGuardStore((state) => state.selectedEntityId);
  const autonomy = useGraphGuardStore((state) => state.autonomy);
  const setSelection = useGraphGuardStore((state) => state.setSelection);
  const selectedEvidenceId = useGraphGuardStore((state) => state.selectedEvidenceId);
  const setSelectedEvidenceId = useGraphGuardStore((state) => state.setSelectedEvidenceId);
  const alertsQuery = useQuery({ queryKey: ["alerts"], queryFn: () => getAlerts() });
  const incidentsQuery = useQuery({ queryKey: ["incidents"], queryFn: getIncidents });
  const [filter, setFilter] = useState("ALL");
  const [running, setRunning] = useState(false);
  const [maxHops, setMaxHops] = useState(4);
  const [progress, setProgress] = useState<InvestigationEvent[]>([]);
  const [liveIncident, setLiveIncident] = useState<Incident | null>(null);
  const [streamFallback, setStreamFallback] = useState(false);
  const [drawerTab, setDrawerTab] = useState<DrawerTab>("evidence");
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const alerts = useMemo(() => alertsQuery.data || [], [alertsQuery.data]);
  const selectedAlert = alerts.find((alert) => alert.id === selectedAlertId) || null;
  const persistedIncident = incidentsQuery.data?.find((item) => item.alert_id === selectedAlert?.id) || null;
  const detailQuery = useQuery({ queryKey: ["incident", persistedIncident?.id], queryFn: () => getIncident(persistedIncident!.id), enabled: Boolean(persistedIncident?.id && !liveIncident) });
  const storedIncident = detailQuery.data || persistedIncident;
  const incident = liveIncident || storedIncident;
  const evidenceQuery = useQuery({ queryKey: ["incident-evidence", incident?.id], queryFn: () => getIncidentEvidence(incident!.id), enabled: Boolean(incident?.id && !liveIncident) });
  const evidence = liveIncident?.evidence || evidenceQuery.data || [];
  const neighborhoodQuery = useQuery({ queryKey: ["neighborhood", selectedEntityId, maxHops], queryFn: () => getNeighborhood(selectedEntityId as string, maxHops), enabled: Boolean(selectedEntityId) });
  const filteredAlerts = useMemo(() => filter === "ALL" ? alerts : alerts.filter((alert) => String(alert.status || "").toUpperCase() === filter), [alerts, filter]);

  useEffect(() => { if (!selectedAlertId && alerts[0]) setSelection(alerts[0]); }, [alerts, selectedAlertId, setSelection]);
  useEffect(() => { setLiveIncident(null); setProgress([]); setError(""); setMessage(""); setDrawerTab("evidence"); }, [selectedAlertId]);

  function selectAlert(alert: Alert) { setSelection(alert); }
  function handleError(value: string) { setError(value); setMessage(""); }
  async function runInvestigation() {
    if (!selectedAlert || running) return;
    setRunning(true); setError(""); setMessage(""); setProgress([]); setLiveIncident(null);
    let state: InvestigationState | null = null;
    try {
      await streamInvestigation({ alert_id: selectedAlert.id, entity_id: selectedAlert.entity_id }, (event) => { setProgress((current) => [...current, event]); if (event.state) state = event.state; if (event.message) setMessage(String(event.message)); });
    } catch (streamError) {
      setStreamFallback(true);
      try { state = await investigate({ alert_id: selectedAlert.id, entity_id: selectedAlert.entity_id, autonomy_mode: autonomy || "APPROVE" }); setMessage("Streaming was unavailable; investigation completed through the request fallback."); } catch (fallbackError) { handleError(fallbackError instanceof Error ? fallbackError.message : streamError instanceof Error ? streamError.message : "Investigation failed"); setRunning(false); return; }
    }
    if (state) {
      const normalized = incidentFromState(state);
      if (normalized) { try { const [full, storedEvidence] = await Promise.all([getIncident(normalized.id), getIncidentEvidence(normalized.id)]); setLiveIncident({ ...full, evidence: storedEvidence }); } catch { setLiveIncident({ ...normalized, evidence: state.evidence_items }); } }
      await queryClient.invalidateQueries({ queryKey: ["incidents"] });
      setDrawerTab("evidence"); setMessage("Investigation complete. Evidence and policy results are stored by the backend.");
    }
    setRunning(false);
  }

  return <div className="page-stack"><div className="page-heading"><div><div className="eyebrow">/ active queue / evidence-grounded response</div><h1>Investigation workspace</h1><p className="subheading">Inspect connected signals, preserve the evidence trail, and keep every response reversible.</p></div><div className="heading-actions"><span className="lead-note">Synthetic data · relationships are leads, not proof.</span><GuidedDemo alerts={alerts} autonomy={autonomy} onSelect={selectAlert} onState={(state) => { const normalized = incidentFromState(state); if (normalized) setLiveIncident({ ...normalized, evidence: state.evidence_items }); setProgress(state.progress || []); }} /></div></div>
    <section className="mission-grid" aria-label="Investigation mission control">
      <aside className="queue-pane"><div className="pane-header"><div><div className="pane-title">Alert queue</div><div className="pane-muted">Live alerts from FalkorDB</div></div><span className="pane-count">{alertsQuery.isLoading ? "—" : alerts.length}</span></div><div className="queue-filters">{["ALL", "OPEN", "REVIEW"].map((value) => <button key={value} className={`filter-chip ${filter === value ? "active" : ""}`} onClick={() => setFilter(value)}>{value}</button>)}</div>{alertsQuery.isLoading ? <Loading label="Loading alerts…" /> : alertsQuery.isError ? <ErrorState message="Alerts could not be loaded." retry={() => alertsQuery.refetch()} /> : !filteredAlerts.length ? <EmptyState title="No alerts" body="No alerts match this filter." /> : <div className="alert-list">{filteredAlerts.map((alert) => { const investigated = incidentsQuery.data?.some((item) => item.alert_id === alert.id); return <button key={alert.id} className={`alert-card priority-${priorityNumber(alert.priority)} ${selectedAlert?.id === alert.id ? "selected" : ""}`} onClick={() => selectAlert(alert)}><div className="alert-row"><span className="alert-id mono">{alert.id}</span><span className="alert-time">P{priorityNumber(alert.priority)}</span></div><strong>{alertTitle(alert)}</strong><p>{alert.reason || "No reason supplied by the API."}</p><div className="alert-tags"><span className="mini-tag mono">{alert.entity_id}</span><span className="mini-tag">{String(alert.status || "UNKNOWN")}</span><span className={`mini-tag ${investigated ? "green" : "amber"}`}>{investigated ? "investigated" : "not investigated"}</span></div></button>; })}</div>}</aside>
      <section className="workspace-pane"><div className="workspace-head"><div><div className="eyebrow">{incident ? `CASE / ${incident.id}` : "CASE / not started"}</div><h2>Connected risk surface</h2><p>{selectedEntityId ? `Entity ${selectedEntityId} · bounded ${maxHops}-hop neighborhood` : "Select a live alert to load its graph."}</p></div>{selectedEntityId && <span className="entity-chip mono">{selectedEntityId}</span>}</div>{message && <div className="notice green"><Check size={15} /> {message}</div>}{error && <div className="notice red"><ShieldAlert size={15} /> {error}</div>}<GraphCanvas neighborhood={neighborhoodQuery.data} evidence={evidence} maxHops={maxHops} setMaxHops={setMaxHops} selectedEvidenceId={selectedEvidenceId} onEvidenceSelect={setSelectedEvidenceId} />{neighborhoodQuery.isError && <ErrorState message="The neighborhood query failed; no graph is rendered in its place." retry={() => neighborhoodQuery.refetch()} />}<div className="workspace-metrics">{incident ? <><div className="metric"><span>Risk score</span><strong className="red">{Number(incident.score ?? 0)}/100</strong></div><div className="metric"><span>Evidence</span><strong className="cyan">{evidence.length}</strong></div><div className="metric"><span>Tier</span><strong>{String(incident.tier || "NO_ACTION").replaceAll("_", " ")}</strong></div><div className="metric"><span>Policy</span><strong>{incident.policy_version || "—"}</strong></div></> : <div className="metric metric-wide"><span>Investigation state</span><strong>Not investigated</strong><small>No score or evidence is shown until the backend completes an investigation.</small></div>}</div><div className="progress-section"><div className="section-bar"><span className="section-title">Agent progress</span><span className="section-note">{running ? "RUNNING" : streamFallback ? "POST FALLBACK" : progress.length ? "COMPLETE" : "READY"}</span></div>{running || progress.length ? <div className="progress-list">{progress.map((item, index) => <details className="progress-card" key={`${String(item.event)}-${index}`}><summary><span className="progress-icon">{item.event === "tool_completed" ? <Check size={13} /> : <Clock3 size={13} />}</span><span><strong>{String(item.tool || item.event || "progress").replaceAll("_", " ")}</strong><small>{item.message || (item.result_count !== undefined ? `${item.result_count} result(s)` : item.reason || "Backend event")}</small></span><span className="mono">{item.duration_ms ? `${item.duration_ms}ms` : ""}</span></summary>{item.state && <pre>{JSON.stringify(item.state, null, 2)}</pre>}</details>)}{running && <Loading label="Waiting for the next backend step…" />}</div> : <EmptyState title="Investigation not started" body="Run the real evidence workflow to populate agent progress." />}<button className="button primary run-button" onClick={runInvestigation} disabled={running || !selectedAlert}>{running ? <><LoaderCircle size={15} className="spin" /> Investigating…</> : <><Play size={15} /> Run investigation</>}</button></div></section>
      <aside className="drawer-pane"><div className="drawer-tabs" role="tablist">{(["evidence", "score", "why", "actions", "copilot"] as DrawerTab[]).map((tab) => <button key={tab} role="tab" aria-selected={drawerTab === tab} className={drawerTab === tab ? "active" : ""} onClick={() => setDrawerTab(tab)}>{tab === "why" ? "Why / Why-not" : tab}</button>)}</div>{!incident && <EmptyState title="Evidence drawer is empty" body="Select an alert and run an investigation. No result is invented while the API is offline or before the run completes." />}{incident && drawerTab === "evidence" && <EvidenceView evidence={evidence} selectedEvidenceId={selectedEvidenceId} onSelect={setSelectedEvidenceId} />}{incident && drawerTab === "score" && <ScoreView incident={incident} evidence={evidence} />}{incident && drawerTab === "why" && <WhyView incident={incident} />}{incident && drawerTab === "actions" && <ActionView incident={incident} autonomy={autonomy} onError={handleError} onRefresh={() => { queryClient.invalidateQueries({ queryKey: ["incidents"] }); }} />}{incident && drawerTab === "copilot" && <CopilotView incident={incident} onCitation={setSelectedEvidenceId} />}{incident && <div className="drawer-footer"><Link href="/audit" className="button compact"><FileText size={14} /> Open audit trail <ExternalLink size={13} /></Link><AuditInline /></div>}</aside>
    </section>
  </div>;
}

function AuditInline() { const [state, setState] = useState<"unknown" | "valid" | "invalid">("unknown"); async function verify() { try { const result = await verifyAudit(); setState(result.valid ? "valid" : "invalid"); } catch { setState("unknown"); } } return <div className="audit-inline"><span className={`grounding-badge ${state === "valid" ? "valid" : state === "invalid" ? "invalid" : ""}`}>{state === "valid" ? "Chain valid" : state === "invalid" ? "Chain invalid" : "Not verified"}</span><button className="icon-button" title="Verify audit chain" onClick={verify}><RefreshCw size={14} /></button></div>; }
