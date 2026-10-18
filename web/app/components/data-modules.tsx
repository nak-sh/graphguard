"use client";

import { useEffect, useState } from "react";
import { getAudit, getBenchmark, getContainment, getRedTeamMatrix, getReplay } from "@/lib/api";

function Loading() { return <div className="module-loading" role="status">Loading live FalkorDB result…</div>; }
function ErrorState() { return <div className="module-empty">The API result is not available yet. Run `docker compose up` and refresh.</div>; }

export function ReplayPanel() {
  const [data, setData] = useState<Awaited<ReturnType<typeof getReplay>> | null>(null);
  const [index, setIndex] = useState(0);
  useEffect(() => { getReplay("A-104").then(setData).catch(() => setData(null)); }, []);
  if (!data) return <Loading />;
  const edge = data.edges[index] || {};
  return <div className="module-panel"><div className="module-toolbar"><span>Replay entity / A-104</span><span className="status-badge"><span className="status-dot" /> {data.edges.length} edges</span></div><input aria-label="Replay timeline" type="range" min={0} max={Math.max(0, data.edges.length - 1)} value={index} onChange={(event) => setIndex(Number(event.target.value))} className="timeline" /><div className="replay-frame"><span className="eyebrow">FRAME {String(index + 1).padStart(2, "0")}</span><strong>{String(edge.source || "—")} <span className="flow-arrow">→</span> {String(edge.target || "—")}</strong><span>{String(edge.amount || 0)} volume · t={String(edge.ts || "—")}</span></div><p className="module-note">Cumulative synthetic volume: {data.edges.slice(0, index + 1).reduce((sum, item) => sum + Number(item.amount || 0), 0).toFixed(2)}. Cycle close frame: {data.cycle_close_index ?? "not detected"}.</p></div>;
}

export function ContainmentPanel() {
  const [data, setData] = useState<Record<string, any> | null>(null);
  useEffect(() => { getContainment("A-104").then((value) => setData(value as Record<string, any>)).catch(() => setData(null)); }, []);
  if (!data) return <Loading />;
  return <div className="module-panel"><div className="module-toolbar"><span>FalkorDB evidence → optimizer</span><span className="synthetic-badge"><span className="status-dot" /> ESTIMATES</span></div><div className="tradeoff-grid">{["hold_all", "hold_optimizer_pick", "flag_only"].map((key) => { const card = data[key] || {}; return <div className={`tradeoff-card${key === "hold_optimizer_pick" ? " chosen" : ""}`} key={key}><span className="eyebrow">{key.replaceAll("_", " ")}</span><strong>{card.account_count ?? 0} accounts</strong><span>interrupted: {Number(card.suspicious_volume_interrupted_estimate || 0).toFixed(0)}</span><span>legitimate frozen: {Number(card.legitimate_volume_frozen_estimate || 0).toFixed(0)}</span></div>; })}</div><p className="module-note">Greedy weighted cycle hitting-set plus NetworkX min-cut over the subgraph fetched from FalkorDB. All collateral numbers are synthetic estimates.</p></div>;
}

export function RedTeamPanel() {
  const [data, setData] = useState<Record<string, any> | null>(null);
  useEffect(() => { getRedTeamMatrix().then((value) => setData(value as Record<string, any>)).catch(() => setData(null)); }, []);
  if (!data) return <Loading />;
  return <div className="module-panel"><div className="module-toolbar"><span>{data.execution_status === "complete" ? "Scratch graphs completed" : "Execution partial or blocked"}</span><span className="status-badge"><span className="status-dot" /> HONEST MATRIX</span></div><div className="redteam-list">{(data.variants || []).map((row: Record<string, any>) => <div className="redteam-row" key={row.variant_id}><strong>{row.variant_id}</strong><span>{row.caught ? "CAUGHT" : "MISSED"}</span><span>{(row.signals || []).join(" · ") || "no signal"}</span><small>{row.suggested_policy_knob}</small></div>)}</div><p className="module-note">Misses remain visible. Suggested knobs are hypotheses for a future policy run, not claims of robustness.</p></div>;
}

export function AuditPanel() {
  const [events, setEvents] = useState<Record<string, any>[]>([]);
  const [valid, setValid] = useState<boolean | null>(null);
  useEffect(() => { getAudit().then(setEvents).catch(() => undefined); }, []);
  async function verify() { try { const result = await (await fetch(`${(process.env.NEXT_PUBLIC_API_BASE_URL || "/backend")}/api/audit/verify`, { cache: "no-store" })).json() as { valid: boolean }; setValid(result.valid); } catch { setValid(null); } }
  return <div className="module-panel"><div className="module-toolbar"><span>{events.length} persisted events</span><button className="button" onClick={verify}>Verify chain</button></div><div className="audit-list">{events.slice(-8).map((event) => <div className="audit-row" key={String(event.id)}><span>{String(event.chain_index || "—")}</span><strong>{String(event.action)}</strong><span>{String(event.entity_id)}</span><small>{String(event.id)}</small></div>)}</div><p className="module-note">{valid === true ? "SHA-256 chain verified." : valid === false ? "Chain verification failed; inspect the tamper event." : "Verification has not been run in this view."}</p></div>;
}

export function BenchmarkPanel() {
  const [data, setData] = useState<Record<string, any> | null>(null);
  useEffect(() => { getBenchmark().then((value) => setData(value as Record<string, any>)).catch(() => setData(null)); }, []);
  if (!data) return <ErrorState />;
  const results = (data.results || []) as Record<string, any>[];
  return <div className="module-panel"><div className="module-toolbar"><span>{data.iterations} measured runs · {data.warmups} warmups</span><span className="synthetic-badge"><span className="status-dot" /> MEASURED</span></div><div className="benchmark-list">{results.slice(0, 8).map((row, index) => <div className="benchmark-row" key={`${row.size}-${row.depth}-${index}`}><span>n={row.size} / d={row.depth}</span><strong>graph p50 {row.falkordb?.p50_ms} ms</strong><span>SQL p50 {row.sqlite_recursive_cte?.p50_ms} ms</span></div>)}</div><p className="module-note">{String(data.methodology)}</p></div>;
}

export function PolicyPanel() {
  const [cycleWeight, setCycleWeight] = useState(40);
  const [highThreshold, setHighThreshold] = useState(70);
  const [result, setResult] = useState<Record<string, any> | null>(null);
  const [busy, setBusy] = useState(false);
  async function evaluate() {
    setBusy(true);
    try {
      const base = process.env.NEXT_PUBLIC_API_BASE_URL || "/backend";
      const response = await fetch(`${base}/api/policy/sandbox`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ version: "2026-10-sandbox", thresholds: { high: highThreshold }, weights: { TIME_ORDERED_CYCLE: cycleWeight } }) });
      setResult(await response.json() as Record<string, any>);
    } finally { setBusy(false); }
  }
  return <div className="module-panel"><div className="policy-slider"><label>Cycle weight <output>{cycleWeight}</output><input type="range" min={0} max={60} value={cycleWeight} onChange={(event) => setCycleWeight(Number(event.target.value))} /></label><label>Hold threshold <output>{highThreshold}</output><input type="range" min={40} max={100} value={highThreshold} onChange={(event) => setHighThreshold(Number(event.target.value))} /></label></div><button className="button primary" onClick={evaluate} disabled={busy}>{busy ? "Evaluating cached evidence…" : "Evaluate cached scenarios"}</button>{result && <><div className="module-toolbar" style={{ marginTop: 15 }}><span>Cached evidence only</span><span className={`status-badge${(result.decoy_regressions || []).length ? " offline" : ""}`}><span className="status-dot" /> {(result.decoy_regressions || []).length ? "DECOY REGRESSION" : "NO DECOY REGRESSION"}</span></div><div className="benchmark-list">{(result.rows || []).slice(0, 10).map((row: Record<string, any>) => <div className="benchmark-row" key={String(row.incident_id)}><span>{String(row.entity_id)}</span><strong>{String(row.sandbox_tier)}</strong><span>score {String(row.sandbox_score)}</span></div>)}</div></>}</div>;
}
