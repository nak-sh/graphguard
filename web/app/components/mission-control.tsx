"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import {
  Alert,
  AutonomyMode,
  EvidenceItem,
  Incident,
  dryRunAction,
  executeAction,
  fallbackAlerts,
  getAlerts,
  getHealth,
  getNeighborhood,
  investigate,
  setAutonomy,
  streamInvestigation,
  verifyAudit,
} from "@/lib/api";

type ProgressState = "complete" | "active" | "pending";

const navItems = [
  { href: "/", label: "Overview", icon: "◈" },
  { href: "/investigate", label: "Investigate", icon: "⌕" },
  { href: "/replay", label: "Replay", icon: "↻" },
  { href: "/containment", label: "Contain", icon: "⊘" },
  { href: "/red-team", label: "Red-team", icon: "△" },
  { href: "/policy", label: "Policy", icon: "≡" },
  { href: "/audit", label: "Audit", icon: "✓" },
  { href: "/benchmark", label: "Bench", icon: "∿" },
];

const stages = [
  { key: "ground", title: "Ground alert", body: "Alert and entity context loaded" },
  { key: "neighborhood", title: "Map neighborhood", body: "Bounded graph neighborhood and hubs" },
  { key: "evidence", title: "Assemble evidence", body: "Cycles, paths, and infrastructure checks" },
  { key: "policy", title: "Evaluate policy", body: "Tier and reversible action proposal" },
] as const;

const fallbackEvidence: EvidenceItem[] = [
  { id: "EV-CYC-6b0c1d", kind: "CYCLE", query_name: "detect_transfer_cycles", summary: "Five-hop, time-ordered transfer loop closes on A-104.", flagged: true },
  { id: "EV-SHA-7d2f89", kind: "INFRA", query_name: "find_shared_infrastructure", summary: "DVC-8841 connects four accounts outside hub cutoff.", flagged: true },
  { id: "EV-DEC-1a44c8", kind: "COUNTERFACTUAL", query_name: "compare_decoy", summary: "Household look-alike D-201 has no bad-target confirmation.", flagged: false },
];

const fallbackIncident: Incident = {
  id: "INC-SYN-104",
  alert_id: "ALT-7F31",
  entity_id: "A-104",
  risk_score: 84,
  risk_tier: "AUTO_HOLD",
  tier: "AUTO_HOLD",
  confidence: 0.92,
  approval_status: "PENDING",
  evidence: fallbackEvidence,
  proposed_actions: [{ action_id: "ACT-HOLD-A104", type: "HOLD_ACCOUNT", target_entity: "A-104", tier: "AUTO_HOLD", reason: "Contain the grounded fraud ring entry point" }],
};

function priorityNumber(value: Alert["priority"]): number {
  const numeric = Number(value);
  return Number.isFinite(numeric) ? numeric : 3;
}

function alertTitle(alert: Alert) {
  return alert.title || alert.reason || "Risk signal requires review";
}

function alertTime(alert: Alert) {
  if (!alert.created_at) return "LIVE";
  const value = new Date(alert.created_at).getTime();
  if (!Number.isFinite(value)) return "LIVE";
  const minutes = Math.max(0, Math.round((Date.now() - value) / 60000));
  return minutes < 1 ? "now" : `${minutes}m ago`;
}

export default function MissionControl() {
  const [alerts, setAlerts] = useState<Alert[]>(fallbackAlerts);
  const [selectedId, setSelectedId] = useState(fallbackAlerts[0].id);
  const [incident, setIncident] = useState<Incident>(fallbackIncident);
  const [autonomy, setAutonomyMode] = useState<AutonomyMode>("APPROVE");
  const [apiOnline, setApiOnline] = useState<boolean | null>(null);
  const [activeFilter, setActiveFilter] = useState("OPEN");
  const [running, setRunning] = useState(false);
  const [stage, setStage] = useState(3);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [auditState, setAuditState] = useState<"unknown" | "valid" | "invalid">("unknown");
  const [neighborhood, setNeighborhood] = useState<Awaited<ReturnType<typeof getNeighborhood>> | null>(null);

  useEffect(() => {
    let mounted = true;
    getAlerts()
      .then((rows) => {
        if (!mounted) return;
        if (rows.length) {
          setAlerts(rows);
          setSelectedId(rows[0].id);
        }
        setApiOnline(true);
      })
      .catch(() => mounted && setApiOnline(false));
    getHealth().then((health) => mounted && setApiOnline(health.ok)).catch(() => mounted && setApiOnline(false));
    return () => { mounted = false; };
  }, []);

  const selectedAlert = useMemo(() => alerts.find((alert) => alert.id === selectedId) || alerts[0], [alerts, selectedId]);
  const filteredAlerts = useMemo(() => {
    if (activeFilter === "ALL") return alerts;
    return alerts.filter((alert) => String(alert.status || "OPEN").toUpperCase() === activeFilter) || alerts;
  }, [activeFilter, alerts]);
  const actions = incident.proposed_actions || fallbackIncident.proposed_actions || [];
  const firstAction = actions[0];
  const evidence = (incident.evidence && incident.evidence.length ? incident.evidence : fallbackEvidence) as EvidenceItem[];
  const riskScore = Math.max(0, Math.min(100, Number(incident.risk_score ?? 84)));
  const riskTier = incident.risk_tier || incident.tier || "AUTO_HOLD";

  useEffect(() => {
    if (!selectedAlert?.entity_id) return;
    getNeighborhood(selectedAlert.entity_id)
      .then((graph) => { setNeighborhood(graph); setApiOnline(true); })
      .catch(() => setNeighborhood(null));
  }, [selectedAlert?.entity_id]);

  function selectAlert(alert: Alert) {
    setSelectedId(alert.id);
    setError("");
    setMessage("");
    setStage(0);
    setIncident({ ...fallbackIncident, id: `INC-SYN-${alert.entity_id}`, alert_id: alert.id, entity_id: alert.entity_id });
    setNeighborhood(null);
  }

  async function changeAutonomy(next: AutonomyMode) {
    setAutonomyMode(next);
    setMessage("Saving autonomy policy…");
    try {
      const saved = await setAutonomy(next);
      setAutonomyMode(saved.mode);
      setApiOnline(true);
      setMessage(`Autonomy policy set to ${saved.mode}.`);
    } catch {
      setMessage("Local selector updated; API policy was not reachable.");
      setApiOnline(false);
    }
  }

  async function runInvestigation() {
    if (!selectedAlert || running) return;
    setRunning(true);
    setError("");
    setMessage("Opening evidence stream…");
    setStage(1);
    let streamedIncident: Incident | undefined;
    try {
      await streamInvestigation(
        { alert_id: selectedAlert.id, entity_id: selectedAlert.entity_id },
        (event) => {
          if (event.incident) streamedIncident = event.incident;
          const state = event.state as Record<string, unknown> | undefined;
          if (state && state.incident_id) {
            streamedIncident = {
              id: String(state.incident_id),
              alert_id: selectedAlert.id,
              entity_id: selectedAlert.entity_id,
              risk_score: Number(state.score || 0),
              risk_tier: String(state.tier || "NO_ACTION"),
              tier: String(state.tier || "NO_ACTION"),
              approval_status: String(state.approval_status || "NOT_REQUIRED"),
              evidence: (state.evidence_items as EvidenceItem[] | undefined) || [],
              proposed_actions: state.proposed_actions as Incident["proposed_actions"],
            };
          }
          const eventName = String(event.event || event.step || "").toLowerCase();
          if (eventName.includes("evidence")) setStage(2);
          if (eventName.includes("policy") || eventName.includes("complete")) setStage(3);
          if (event.message) setMessage(event.message);
        },
      );
      if (streamedIncident) setIncident(streamedIncident);
      getNeighborhood(selectedAlert.entity_id).then(setNeighborhood).catch(() => undefined);
      setApiOnline(true);
      setStage(4);
      setMessage("Investigation complete; evidence bundle is ready.");
    } catch {
      try {
        const result = await investigate({ alert_id: selectedAlert.id, entity_id: selectedAlert.entity_id, autonomy_mode: autonomy });
        const state = result as Incident & Record<string, unknown>;
        setIncident({ ...state, risk_score: Number(state.risk_score ?? state.score ?? 0), risk_tier: String(state.risk_tier ?? state.tier ?? "NO_ACTION") });
        getNeighborhood(selectedAlert.entity_id).then(setNeighborhood).catch(() => undefined);
        setApiOnline(true);
        setStage(4);
        setMessage("Investigation complete; evidence bundle is ready.");
      } catch {
        setIncident({ ...fallbackIncident, id: `INC-SYN-${selectedAlert.entity_id}`, alert_id: selectedAlert.id, entity_id: selectedAlert.entity_id });
        setApiOnline(false);
        setStage(4);
        setMessage("Showing deterministic synthetic evidence while the API is offline.");
      }
    } finally {
      setRunning(false);
    }
  }

  async function runDryRun() {
    if (!firstAction) return;
    setError("");
    setMessage("Requesting policy-gated dry run…");
    try {
      await dryRunAction(incident.id, firstAction.action_id);
      setIncident((current) => ({ ...current, dry_run_completed: true }));
      setMessage("Dry run returned a reversible diff.");
      setApiOnline(true);
    } catch {
      setIncident((current) => ({ ...current, dry_run_completed: true }));
      setMessage("Synthetic dry-run preview shown; API response is pending.");
      setApiOnline(false);
    }
  }

  async function executeContainment() {
    if (!firstAction) return;
    setError("");
    setMessage("Submitting containment request…");
    try {
      await executeAction({ incident_id: incident.id, proposed_action_id: firstAction.action_id, target_entity: firstAction.target_entity, type: firstAction.type });
      setMessage("Containment request accepted by the action gateway.");
      setApiOnline(true);
    } catch {
      setError("The action gateway did not accept this request. Review policy state and retry.");
      setApiOnline(false);
    }
  }

  async function verifyAuditChain() {
    setMessage("Verifying audit chain…");
    try {
      const result = await verifyAudit();
      setAuditState(result.valid ? "valid" : "invalid");
      setMessage(result.valid ? "Audit chain verified." : "Audit chain verification failed.");
      setApiOnline(true);
    } catch {
      setAuditState("unknown");
      setMessage("Audit verification requires a reachable API.");
      setApiOnline(false);
    }
  }

  return (
    <div className="app-shell">
      <header className="topbar">
        <Link href="/" className="wordmark" aria-label="GraphGuard home">
          <span className="wordmark-mark" aria-hidden="true">GG</span>
          <span><strong>GRAPHGUARD</strong><span>SECURITY OPERATIONS / V2</span></span>
        </Link>
        <div className="topbar-context"><span>MISSION CONTROL</span><span className="context-slash">/</span><span>INVESTIGATE</span></div>
        <div className="topbar-spacer" />
        <div className="topbar-actions">
          <span className="synthetic-badge"><span className="status-dot" /> SYNTHETIC DATA</span>
          <span className={`status-badge${apiOnline === false ? " offline" : ""}`}><span className="status-dot" /> {apiOnline === false ? "API OFFLINE" : "FASTAPI"}</span>
          <label className="autonomy-control"><span>Autonomy</span><select aria-label="Autonomy mode" value={autonomy} onChange={(event) => changeAutonomy(event.target.value as AutonomyMode)}><option value="OBSERVE">Observe</option><option value="RECOMMEND">Recommend</option><option value="APPROVE">Approve</option><option value="AUTO_WITHIN_LIMITS">Auto / limits</option></select></label>
        </div>
      </header>

      <div className="app-body">
        <nav className="rail" aria-label="Primary navigation">
          {navItems.map((item) => <Link key={item.href} href={item.href} className={`rail-link${item.href === "/" ? " active" : ""}`}><span className="rail-icon" aria-hidden="true">{item.icon}</span><span className="rail-label">{item.label}</span></Link>)}
          <span className="rail-bottom">OPERATIONS / 07</span>
        </nav>

        <main className="main-canvas">
          <div className="page-heading">
            <div><div className="eyebrow">/ active queue / evidence-grounded response</div><h1>Investigation workspace</h1><p className="subheading">Triage connected risk signals, inspect their graph neighborhood, and keep every response reversible.</p></div>
            <div className="heading-meta"><span className="live">● LIVE QUEUE</span><span>updated just now</span></div>
          </div>

          <section className="mission-grid" aria-label="Investigation mission control">
            <aside className="queue-pane" aria-label="Alert queue">
              <div className="pane-header" style={{ padding: "16px 14px 13px" }}><div><div className="pane-title">Alert queue</div><div className="pane-muted" style={{ marginTop: 4 }}>Priority-sorted signals</div></div><span className="pane-count">{alerts.length.toString().padStart(2, "0")}</span></div>
              <div className="queue-filters" role="group" aria-label="Alert filters">
                {['OPEN', 'REVIEW', 'ALL'].map((filter) => <button key={filter} className={`filter-chip${activeFilter === filter ? " active" : ""}`} onClick={() => setActiveFilter(filter)}>{filter}</button>)}
              </div>
              <div className="alert-list">
                {filteredAlerts.map((alert) => <button key={alert.id} className={`alert-card priority-${priorityNumber(alert.priority)}${selectedId === alert.id ? " selected" : ""}`} onClick={() => selectAlert(alert)}><span className="alert-row"><span className="alert-id">{alert.id}</span><span className="alert-time">{alertTime(alert)}</span></span><span className="alert-title">{alertTitle(alert)}</span><span className="alert-reason">{alert.reason || "Graph signal queued for analyst review"}</span><span className="alert-tags"><span className={`mini-tag ${priorityNumber(alert.priority) === 1 ? "high" : ""}`}>P{priorityNumber(alert.priority)}</span><span className="mini-tag">{alert.entity_id}</span><span className="mini-tag open">{String(alert.status || "OPEN")}</span></span></button>)}
                {!filteredAlerts.length && <div className="pane-muted" style={{ padding: 16 }}>No alerts match this filter.</div>}
              </div>
            </aside>

            <section className="workspace-pane" aria-label="Graph investigation">
              <div className="workspace-head"><div><div className="eyebrow">CASE / {incident.id}</div><h2>Connected risk surface</h2><p>Bounded neighborhood · 4 hops · hub-aware</p></div><span className="entity-chip">{selectedAlert?.entity_id || "A-104"}</span></div>
              {message && <div className="toast" role="status">{message}</div>}
              {error && <div className="error-note" role="alert">{error}</div>}
              <div className="graph-card" aria-label="Synthetic graph neighborhood visualization">
                <div className="graph-grid" />
                <svg className="graph-svg" viewBox="0 0 620 282" role="img" aria-label="Account neighborhood with transfer cycle and shared device">
                  <defs><marker id="arrow" markerWidth="7" markerHeight="7" refX="6" refY="3.5" orient="auto"><path d="M0,0 L7,3.5 L0,7 z" fill="#405566" /></marker><marker id="arrow-hot" markerWidth="7" markerHeight="7" refX="6" refY="3.5" orient="auto"><path d="M0,0 L7,3.5 L0,7 z" fill="#f07878" /></marker></defs>
                  {neighborhood && neighborhood.nodes.length > 0 ? (() => {
                    const visible = neighborhood.nodes.slice(0, 48);
                    const positions = new Map(visible.map((node, index) => {
                      const angle = (index / Math.max(visible.length, 1)) * Math.PI * 2;
                      const radius = Math.min(105, 42 + visible.length * 2.1);
                      return [node.id, { x: 310 + Math.cos(angle) * radius, y: 140 + Math.sin(angle) * radius }] as const;
                    }));
                    return <>
                      {neighborhood.edges.slice(0, 90).map((edge, index) => {
                        const source = positions.get(edge.source); const target = positions.get(edge.target);
                        if (!source || !target) return null;
                        const hot = edge.relationship === "SENT_MONEY";
                        return <line key={`${edge.source}-${edge.target}-${index}`} className={`graph-edge${hot ? " hot" : ""}`} x1={source.x} y1={source.y} x2={target.x} y2={target.y} markerEnd={hot ? "url(#arrow-hot)" : "url(#arrow)"} />;
                      })}
                      {visible.map((node) => {
                        const point = positions.get(node.id)!; const label = node.label; const status = String(node.properties?.status || "");
                        const account = label === "Account"; const hub = neighborhood.hub_nodes?.includes(node.id);
                        return <g key={node.id} className="graph-node-group"><circle className={`graph-node ${account ? (status === "HOLD" ? "hot" : "") : label === "Device" ? "device" : "ip"}`} cx={point.x} cy={point.y} r={account ? 18 : 13} /><text className="graph-text" x={point.x} y={point.y}>{node.id.length > 10 ? `${node.id.slice(0, 9)}…` : node.id}</text>{hub && <text className="graph-hub" x={point.x} y={point.y + 27}>HUB</text>}</g>;
                      })}
                    </>;
                  })() : <>
                  <path className="graph-edge hot" markerEnd="url(#arrow-hot)" d="M130 143 C170 70, 250 63, 292 109" /><path className="graph-edge hot" markerEnd="url(#arrow-hot)" d="M292 109 C353 158, 384 180, 458 140" /><path className="graph-edge hot" markerEnd="url(#arrow-hot)" d="M458 140 C407 224, 217 239, 130 143" /><path className="graph-edge" markerEnd="url(#arrow)" d="M130 143 L95 67" /><path className="graph-edge" markerEnd="url(#arrow)" d="M292 109 L308 40" /><path className="graph-edge" markerEnd="url(#arrow)" d="M458 140 L535 75" /><path className="graph-edge" d="M130 143 L301 228" /><path className="graph-edge" d="M458 140 L301 228" />
                  <circle className="graph-node hot" cx="130" cy="143" r="28" /><circle className="graph-node hot" cx="292" cy="109" r="25" /><circle className="graph-node hot" cx="458" cy="140" r="27" /><circle className="graph-node" cx="95" cy="67" r="20" /><circle className="graph-node" cx="308" cy="40" r="20" /><circle className="graph-node" cx="535" cy="75" r="20" /><circle className="graph-node device" cx="301" cy="228" r="24" />
                  <text className="graph-text" x="130" y="143">A-104</text><text className="graph-text" x="292" y="109">A-109</text><text className="graph-text" x="458" y="140">A-117</text><text className="graph-text" x="95" y="67">A-088</text><text className="graph-text" x="308" y="40">IP-21</text><text className="graph-text" x="535" y="75">A-122</text><text className="graph-text" x="301" y="228">DVC-8841</text>
                  </>}
                </svg>
                <div className="graph-label">GRAPH SNAPSHOT / SYN-04</div><div className="graph-legend"><span className="legend-item"><i className="legend-dot" /> flagged account</span><span className="legend-item"><i className="legend-dot device" /> device</span><span className="legend-item"><i className="legend-dot ip" /> shared IP</span></div>
              </div>
              <div className="workspace-metrics"><div className="metric"><div className="metric-label">Risk score</div><div className="metric-value red">{riskScore}/100</div></div><div className="metric"><div className="metric-label">Cycle length</div><div className="metric-value amber">05 hops</div></div><div className="metric"><div className="metric-label">Evidence</div><div className="metric-value cyan">{evidence.length.toString().padStart(2, "0")} items</div></div><div className="metric"><div className="metric-label">Policy tier</div><div className="metric-value">{riskTier.replace("_", " ")}</div></div></div>
              <div className="progress-section"><div className="section-bar"><span className="section-title">Investigation progress</span><span className="section-note">{stage >= 4 ? "COMPLETE" : running ? "STREAMING" : "READY"}</span></div><div className="progress-list">{stages.map((item, index) => { const state: ProgressState = stage > index ? "complete" : stage === index ? "active" : "pending"; return <div className={`progress-card ${state}`} key={item.key}><span className="progress-icon">{state === "complete" ? "✓" : state === "active" ? "…" : "·"}</span><span><strong>{item.title}</strong><p>{item.body}</p></span><span className="progress-state">{state}</span></div>; })}</div><button className="button primary" style={{ marginTop: 11, width: "100%" }} onClick={runInvestigation} disabled={running || !selectedAlert}>{running ? "Running evidence stream…" : "Run investigation  →"}</button></div>
            </section>

            <aside className="drawer-pane" aria-label="Evidence and action drawer">
              <div className="drawer-section"><div className="drawer-title">Risk assessment</div><div className="drawer-subtitle">Policy score / deterministic checks</div><div className="risk-wrap"><div className="risk-gauge"><svg viewBox="0 0 100 100" aria-hidden="true"><path className="gauge-track" d="M 15 65 A 35 35 0 0 1 85 65" /><path className="gauge-progress" style={{ strokeDasharray: `${Math.round(riskScore * 1.42)} 200` }} d="M 15 65 A 35 35 0 0 1 85 65" /></svg><div className="risk-score">{riskScore}</div></div><div><div className="risk-caption">{riskTier.replace("_", " ")}</div><p className="risk-copy">{Math.round(Number(incident.confidence ?? .92) * 100)}% confidence from grounded evidence</p></div></div></div>
              <div className="drawer-section"><div className="drawer-title">Evidence bundle</div><div className="drawer-subtitle">Hash-linked observations</div><div className="evidence-list">{evidence.map((item) => <div className={`evidence-item${item.flagged ? " flagged" : ""}`} key={item.id}><strong>{item.kind} / {item.id}</strong><p>{item.summary}</p><div className="evidence-meta"><span>{item.query_name}</span><span>{item.flagged ? "FLAGGED" : "CLEARED"}</span></div></div>)}</div><Link href="/investigate" className="button" style={{ display: "block", marginTop: 9, textDecoration: "none" }}>Open full evidence view  ↗</Link></div>
              <div className="drawer-section"><div className="drawer-title">Response proposal</div><div className="drawer-subtitle">Reversible action · {firstAction?.action_id || "ACT-HOLD-A104"}</div><div className="diff-block"><span className="diff-line dim">// dry-run diff</span><span className="diff-line minus">- status: ACTIVE</span><span className="diff-line plus">+ status: HOLD</span><span className="diff-line plus">+ audit: append-only</span><span className="diff-line dim">  target: {firstAction?.target_entity || selectedAlert?.entity_id || "A-104"}</span></div><div className="drawer-actions"><button className="button" onClick={runDryRun}>{incident.dry_run_completed ? "↻ Re-run dry run" : "Preview dry run"}</button><button className="button danger" onClick={executeContainment} disabled={!incident.dry_run_completed}>Execute containment</button></div><p className="action-note">Execution remains subject to the selected autonomy mode, incident approval, and the FastAPI action gateway.</p></div>
              <div className="drawer-section"><div className="drawer-title">Audit verification</div><div className="drawer-subtitle">Cryptographic chain of custody</div><div style={{ display: "flex", alignItems: "center", gap: 8, marginTop: 11 }}><span className={`status-badge${auditState === "invalid" ? " offline" : ""}`}><span className="status-dot" /> {auditState === "valid" ? "CHAIN VALID" : auditState === "invalid" ? "CHAIN INVALID" : "NOT VERIFIED"}</span><button className="button" style={{ padding: "6px 8px" }} onClick={verifyAuditChain}>Verify</button></div></div>
            </aside>
          </section>
        </main>
      </div>
    </div>
  );
}
