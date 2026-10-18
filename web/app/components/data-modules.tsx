"use client";

import { useEffect, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Bar, BarChart, CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { Check, Copy, FileClock, LoaderCircle, Play, ShieldAlert, TriangleAlert } from "lucide-react";
import { getAudit, getBenchmark, getContainment, getPolicyCurrent, getRedTeamMatrix, getReplay, runPolicySandbox, savePolicySandbox, simulateTampering, verifyAudit, type AuditEvent, type BenchmarkResult, type ContainmentOption, type PolicyModel, type PolicySandboxResult, type RedTeamVariant } from "@/lib/api";
import { useGraphGuardStore } from "@/lib/store";

function Loading({ label = "Loading live result…" }: { label?: string }) { return <div className="empty-state loading-state"><LoaderCircle size={17} className="spin" />{label}</div>; }
function ErrorState({ message, retry }: { message: string; retry: () => void }) { return <div className="empty-state error-state"><ShieldAlert size={18} /><div><strong>Live result unavailable</strong><p>{message}</p><button className="button compact" onClick={retry}>Retry</button></div></div>; }
function NoSelection({ title }: { title: string }) { return <div className="module-panel"><div className="empty-state"><TriangleAlert size={18} /><div><strong>{title}</strong><p>Select an alert on the Investigate page first. This view never substitutes a default entity.</p></div></div></div>; }
function formatNumber(value: unknown) { const number = Number(value); return Number.isFinite(number) ? number.toLocaleString(undefined, { maximumFractionDigits: 2 }) : "—"; }

export function ReplayPanel() {
  const entityId = useGraphGuardStore((state) => state.selectedEntityId);
  const query = useQuery({ queryKey: ["replay", entityId], queryFn: () => getReplay(entityId as string), enabled: Boolean(entityId) });
  const [index, setIndex] = useState(0);
  const [playing, setPlaying] = useState(false);
  useEffect(() => { if (!playing || !query.data?.edges.length) return; const timer = setInterval(() => setIndex((current) => current >= query.data!.edges.length - 1 ? (setPlaying(false), current) : current + 1), 700); return () => clearInterval(timer); }, [playing, query.data]);
  if (!entityId) return <NoSelection title="Replay needs a selected entity" />;
  if (query.isLoading) return <Loading />;
  if (query.isError) return <ErrorState message="Replay could not be loaded from FalkorDB." retry={() => query.refetch()} />;
  const data = query.data;
  if (!data || !data.edges.length) return <div className="module-panel"><div className="empty-state"><TriangleAlert size={18} /><div><strong>No timestamped transfers returned</strong><p>The selected entity has no replay frames in the backend response.</p></div></div></div>;
  const edge = data.edges[Math.min(index, data.edges.length - 1)];
  return <div className="module-panel"><div className="module-toolbar"><span>Replay entity / <b className="mono">{entityId}</b></span><span className="badge cyan">{data.edges.length} frames</span></div><div className="replay-hero"><div className="replay-flow"><span className="mono">{edge.source}</span><span className="replay-arrow">→</span><span className="mono">{edge.target}</span></div><span>Frame {index + 1} · {formatNumber(edge.amount)} volume · t={edge.ts ?? "—"}</span>{edge.cycle_closed && <strong className="cycle-close">Ring closed at t={edge.ts ?? "—"}</strong>}</div><div className="replay-controls"><button className="button compact" onClick={() => setPlaying((value) => !value)}>{playing ? "Pause" : "Play"}</button><input aria-label="Replay timeline" type="range" min={0} max={data.edges.length - 1} value={index} onChange={(event) => setIndex(Number(event.target.value))} /><span className="mono">{formatNumber(edge.cumulative_volume)} cumulative</span></div><div className="replay-track">{data.edges.map((frame, frameIndex) => <button key={`${frame.source}-${frame.target}-${frameIndex}`} className={`replay-segment ${frameIndex === index ? "active" : ""} ${frame.cycle_closed ? "close" : ""}`} onClick={() => setIndex(frameIndex)} title={`${frame.source} → ${frame.target}`} />)}</div><p className="module-note">The backend returned these edges sorted by timestamp. Cumulative volume and cycle-close state are rendered exactly as returned.</p></div>;
}

function TradeoffCard({ label, option, selected, onClick }: { label: string; option: ContainmentOption; selected: boolean; onClick: () => void }) { return <button className={`tradeoff-card ${selected ? "chosen" : ""}`} onClick={onClick}><span className="eyebrow">{label}</span><strong>{option.account_count} accounts</strong><span>Suspicious volume interrupted: {formatNumber(option.suspicious_volume_interrupted_estimate)}</span><span>Legitimate volume frozen: {formatNumber(option.legitimate_volume_frozen_estimate)}</span><small>Estimates over synthetic data</small></button>; }

export function ContainmentPanel() {
  const entityId = useGraphGuardStore((state) => state.selectedEntityId);
  const query = useQuery({ queryKey: ["containment", entityId], queryFn: () => getContainment(entityId as string), enabled: Boolean(entityId) });
  const [choice, setChoice] = useState<"hold_all" | "hold_optimizer_pick" | "flag_only">("hold_optimizer_pick");
  if (!entityId) return <NoSelection title="Containment needs a selected entity" />;
  if (query.isLoading) return <Loading />;
  if (query.isError) return <ErrorState message="Containment options could not be loaded." retry={() => query.refetch()} />;
  const data = query.data; if (!data) return null;
  const options = [data.hold_all, data.hold_optimizer_pick, data.flag_only];
  const chart = options.map((option, index) => ({ name: ["Hold all", "Optimizer", "Flag only"][index], suspicious: option.suspicious_volume_interrupted_estimate, legitimate: option.legitimate_volume_frozen_estimate }));
  return <div className="module-panel"><div className="module-toolbar"><span>Containment optimizer / <b className="mono">{entityId}</b></span><span className="badge amber">Synthetic estimates</span></div><div className="tradeoff-grid"><TradeoffCard label="Hold all" option={data.hold_all} selected={choice === "hold_all"} onClick={() => setChoice("hold_all")} /><TradeoffCard label="Optimizer pick" option={data.hold_optimizer_pick} selected={choice === "hold_optimizer_pick"} onClick={() => setChoice("hold_optimizer_pick")} /><TradeoffCard label="Flag only" option={data.flag_only} selected={choice === "flag_only"} onClick={() => setChoice("flag_only")} /></div><div className="chart-panel"><div className="section-head"><div><span className="eyebrow">Trade-off view</span><h3>Interrupted vs frozen</h3></div><span className="mono">choice: {choice}</span></div><ResponsiveContainer width="100%" height={260}><BarChart data={chart}><CartesianGrid strokeDasharray="3 3" stroke="#273442" /><XAxis dataKey="name" stroke="#9aa7b5" /><YAxis stroke="#9aa7b5" /><Tooltip contentStyle={{ background: "#111a23", border: "1px solid #344554", color: "#e6edf5" }} /><Legend /><Bar dataKey="suspicious" name="Suspicious volume interrupted" fill="#56d6e8" /><Bar dataKey="legitimate" name="Legitimate volume frozen" fill="#f2b45f" /></BarChart></ResponsiveContainer></div><div className="account-set"><span className="eyebrow">Selected account set</span><div>{data[choice].accounts.length ? data[choice].accounts.map((account) => <span className="badge cyan mono" key={account}>{account}</span>) : <span className="muted">No account changes in this option.</span>}</div></div><p className="module-note">{data.method}. All collateral numbers are estimates over synthetic data; a graph connection is a lead, not proof.</p></div>;
}

export function RedTeamPanel() {
  const query = useQuery({ queryKey: ["red-team"], queryFn: getRedTeamMatrix });
  if (query.isLoading) return <Loading />;
  if (query.isError) return <ErrorState message="The red-team matrix could not be loaded." retry={() => query.refetch()} />;
  const data = query.data; if (!data) return null;
  return <div className="module-panel"><div className="module-toolbar"><span>{typeof data.isolated_scratch_graphs === "number" ? `${data.isolated_scratch_graphs} isolated scratch graphs` : data.isolated_scratch_graphs.join(", ")}</span><span className={`badge ${data.execution_status === "complete" ? "green" : "amber"}`}>{data.execution_status}</span></div><div className="matrix-table"><div className="matrix-header"><span>Variant</span><span>Outcome</span><span>Signals</span><span>Suggested knob</span></div>{data.variants.map((row) => <div className={`matrix-row ${row.caught === false ? "missed" : ""}`} key={row.variant_id}><strong>{row.variant_id}</strong><span className={`badge ${row.caught ? "green" : "red"}`}>{row.caught ? "CAUGHT" : "MISSED"}</span><span>{row.signals?.join(" · ") || "No signal returned"}</span><span>{row.suggested_policy_knob || "No suggestion returned"}</span></div>)}</div>{data.honest_misses.length > 0 && <div className="notice red"><ShieldAlert size={15} /> Honest misses: {data.honest_misses.join(", ")}</div>}<p className="module-note">Execution status and misses are rendered from the backend matrix. Suggested knobs are hypotheses, not robustness claims.</p></div>;
}

export function AuditPanel() {
  const query = useQuery({ queryKey: ["audit"], queryFn: getAudit });
  const [valid, setValid] = useState<boolean | null>(null);
  const [tamperResult, setTamperResult] = useState<string | null>(null);
  async function verify() { try { setValid((await verifyAudit()).valid); } catch { setValid(null); } }
  if (query.isLoading) return <Loading />;
  if (query.isError) return <ErrorState message="The audit trail could not be loaded." retry={() => query.refetch()} />;
  const events = query.data || [];
  async function tamper(event: AuditEvent) { try { const result = await simulateTampering(event.id); setTamperResult(result.valid_after ? "Backend reported the chain valid after the control." : "Backend reported the chain invalid after tampering."); setValid(result.valid_after); query.refetch(); } catch (error) { setTamperResult(error instanceof Error ? error.message : "Dev control unavailable"); } }
  return <div className="module-panel"><div className="module-toolbar"><span>{events.length} persisted events</span><div className="toolbar-actions"><button className="button compact" onClick={verify}><Check size={14} /> Verify chain</button>{valid !== null && <span className={`badge ${valid ? "green" : "red"}`}>{valid ? "VALID" : "INVALID"}</span>}</div></div>{!events.length ? <div className="empty-state"><FileClockIcon /><div><strong>No audit events</strong><p>Action and rollback events will appear here after a real backend mutation.</p></div></div> : <div className="audit-timeline">{events.slice().reverse().map((event) => <div className="audit-event" key={event.id}><div className="timeline-dot" /><div className="audit-event-head"><span className="mono">{event.chain_index ?? "—"}</span><strong>{event.action || "event"}</strong><span>{event.entity_id || "—"}</span></div><div className="audit-event-meta"><span>{event.actor || "—"}</span><span className="mono">{event.event_hash ? `${event.event_hash.slice(0, 16)}…` : "no hash"}</span><button className="icon-button" title="Copy event hash" onClick={() => event.event_hash && navigator.clipboard?.writeText(event.event_hash)}><Copy size={13} /></button>{process.env.NEXT_PUBLIC_GRAPHGUARD_DEV_CONTROLS === "1" && <button className="text-button danger-text" onClick={() => tamper(event)}>Simulate tampering</button>}</div></div>)}</div>}{tamperResult && <div className="notice amber">{tamperResult}</div>}<p className="module-note">The chain status is reported by the backend verifier. Dev-only tampering is shown only when the frontend dev flag is enabled.</p></div>;
}

function FileClockIcon() { return <FileClock size={18} />; }

export function BenchmarkPanel() {
  const query = useQuery({ queryKey: ["benchmark"], queryFn: getBenchmark });
  if (query.isLoading) return <Loading />;
  if (query.isError) return <ErrorState message="No benchmark artifact is available. Run `make benchmark` and retry." retry={() => query.refetch()} />;
  const data = query.data; if (!data) return null;
  const points = data.results.map((row) => ({ ...row, label: `n=${row.size} / d=${row.depth}`, graphP50: row.falkordb?.p50_ms, sqlP50: row.sqlite_recursive_cte?.p50_ms, graphP95: row.falkordb?.p95_ms, sqlP95: row.sqlite_recursive_cte?.p95_ms }));
  return <div className="module-panel"><div className="module-toolbar"><span>{data.iterations} iterations · {data.warmups} warmups</span><span className="badge green">Measured</span></div><div className="chart-panel"><div className="section-head"><div><span className="eyebrow">Measured latency</span><h3>Graph vs recursive SQL</h3></div></div><ResponsiveContainer width="100%" height={310}><LineChart data={points}><CartesianGrid strokeDasharray="3 3" stroke="#273442" /><XAxis dataKey="label" stroke="#9aa7b5" /><YAxis stroke="#9aa7b5" unit=" ms" /><Tooltip contentStyle={{ background: "#111a23", border: "1px solid #344554" }} /><Legend /><Line type="monotone" dataKey="graphP50" name="FalkorDB p50" stroke="#56d6e8" /><Line type="monotone" dataKey="sqlP50" name="SQL p50" stroke="#f2b45f" /><Line type="monotone" dataKey="graphP95" name="FalkorDB p95" stroke="#ae9cff" /><Line type="monotone" dataKey="sqlP95" name="SQL p95" stroke="#f07878" /></LineChart></ResponsiveContainer></div><div className="benchmark-table">{points.map((row) => <div className="benchmark-row" key={`${row.size}-${row.depth}`}><span className="mono">n={row.size} · depth {row.depth}</span><span>Graph p50 {formatNumber(row.graphP50)} ms / p95 {formatNumber(row.graphP95)} ms</span><span>SQL p50 {formatNumber(row.sqlP50)} ms / p95 {formatNumber(row.sqlP95)} ms</span></div>)}</div><p className="module-note">{data.methodology} Values are rendered exactly as measured; SQL competitiveness is shown rather than hidden.</p></div>;
}

export function PolicyPanel() {
  const current = useQuery({ queryKey: ["policy-current"], queryFn: getPolicyCurrent });
  const incidents = useQuery({ queryKey: ["incidents"], queryFn: async () => (await import("@/lib/api")).getIncidents() });
  const [policy, setPolicy] = useState<PolicyModel | null>(null);
  const [thresholds, setThresholds] = useState<Record<string, number>>({});
  const [weights, setWeights] = useState<Record<string, number>>({});
  const [result, setResult] = useState<PolicySandboxResult | null>(null);
  const [busy, setBusy] = useState(false);
  useEffect(() => { if (current.data) { setPolicy(current.data); setThresholds(current.data.thresholds); setWeights(Object.fromEntries(Object.entries(current.data.signals).map(([key, value]) => [key, Number(value.weight || 0)]))); } }, [current.data]);
  if (current.isLoading) return <Loading label="Loading active policy…" />;
  if (current.isError || !policy) return <ErrorState message="The active policy could not be loaded from the backend." retry={() => current.refetch()} />;
  const activePolicy = policy;
  async function evaluate() { setBusy(true); try { setResult(await runPolicySandbox({ version: `${activePolicy.version}-sandbox`, thresholds, weights })); } catch (error) { setResult({ policy: activePolicy, rows: [{ incident_id: "error", error: error instanceof Error ? error.message : "Sandbox failed" }], decoy_regressions: [], cached_evidence_only: true }); } finally { setBusy(false); } }
  async function save() { setBusy(true); try { await savePolicySandbox({ version: `${activePolicy.version}-sandbox`, thresholds, weights }); } finally { setBusy(false); } }
  const signalEntries = Object.entries(weights);
  return <div className="module-panel"><div className="module-toolbar"><span>Active policy <b className="mono">{policy.version}</b></span><span className="badge violet">Cached evidence only</span></div><div className="policy-controls">{signalEntries.map(([name, value]) => <label key={name}><span>{name.replaceAll("_", " ")}</span><output>{value}</output><input type="range" min={-30} max={60} value={value} onChange={(event) => setWeights((old) => ({ ...old, [name]: Number(event.target.value) }))} /></label>)}{Object.entries(thresholds).map(([name, value]) => <label key={name}><span>Threshold · {name.replaceAll("_", " ")}</span><output>{value}</output><input type="range" min={0} max={100} value={value} onChange={(event) => setThresholds((old) => ({ ...old, [name]: Number(event.target.value) }))} /></label>)}</div><div className="toolbar-actions"><button className="button primary" disabled={busy || !incidents.data?.length} onClick={evaluate}>{busy ? "Evaluating…" : "Evaluate cached scenarios"}</button><button className="button" disabled={busy || !result} onClick={save}>Save as new version</button></div>{result && <div className="policy-results"><div className={`notice ${result.decoy_regressions.length ? "red" : "green"}`}>{result.decoy_regressions.length ? `Decoy regression: ${result.decoy_regressions.length}` : "No decoy regression reported"}</div>{result.rows.map((row) => <div className={`policy-row ${row.decoy_regression ? "regression" : ""}`} key={row.incident_id}><span className="mono">{row.entity_id || row.incident_id}</span>{row.error ? <span className="danger-text">{row.error}</span> : <><span>{row.original_tier || "—"} → {row.sandbox_tier || "—"}</span><strong>{row.sandbox_score ?? "—"}</strong>{row.decoy_regression && <span className="badge red">DECOY ESCALATION</span>}</>}</div>)}</div>}<p className="module-note">Policy values come from the backend&apos;s active version. Sandbox evaluation uses cached incident evidence and does not re-query relationships.</p></div>;
}
