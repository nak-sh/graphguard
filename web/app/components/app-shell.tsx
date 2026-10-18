"use client";

import * as React from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { Command } from "cmdk";
import { toast, Toaster } from "sonner";
import { Activity, BarChart3, CircleDot, FileClock, FlaskConical, Gauge, GitBranch, Keyboard, ShieldCheck, Undo2 } from "lucide-react";
import { getAutonomy, getHealth, getPolicyCurrent, setAutonomy, type AutonomyMode } from "@/lib/api";
import { useGraphGuardStore } from "@/lib/store";

export const navItems = [
  { href: "/", label: "Investigate", icon: Activity },
  { href: "/replay", label: "Replay", icon: GitBranch },
  { href: "/containment", label: "Containment", icon: ShieldCheck },
  { href: "/red-team", label: "Red-Team", icon: FlaskConical },
  { href: "/policy", label: "Policy", icon: Gauge },
  { href: "/audit", label: "Audit", icon: FileClock },
  { href: "/benchmark", label: "Benchmark", icon: BarChart3 },
];

const autonomyLabels: Record<AutonomyMode, string> = { OBSERVE: "Observe", RECOMMEND: "Recommend", APPROVE: "Approve", AUTO_WITHIN_LIMITS: "Auto / limits" };

export default function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const setHealth = useGraphGuardStore((state) => state.setHealth);
  const setOffline = useGraphGuardStore((state) => state.setApiOffline);
  const autonomy = useGraphGuardStore((state) => state.autonomy);
  const setAutonomyLocal = useGraphGuardStore((state) => state.setAutonomy);
  const health = useGraphGuardStore((state) => state.health);
  const policyVersion = useGraphGuardStore((state) => state.policyVersion);
  const [savingAutonomy, setSavingAutonomy] = React.useState(false);
  const [paletteOpen, setPaletteOpen] = React.useState(false);
  const healthQuery = useQuery({ queryKey: ["health"], queryFn: getHealth, refetchInterval: 20_000 });
  const autonomyQuery = useQuery({ queryKey: ["autonomy"], queryFn: getAutonomy });
  const policyQuery = useQuery({ queryKey: ["policy-current"], queryFn: getPolicyCurrent });

  React.useEffect(() => {
    if (healthQuery.data) { setHealth(healthQuery.data); setOffline(!healthQuery.data.ok); }
    if (healthQuery.isError) setOffline(true);
  }, [healthQuery.data, healthQuery.isError, setHealth, setOffline]);
  React.useEffect(() => { if (autonomyQuery.data?.mode) setAutonomyLocal(autonomyQuery.data.mode); }, [autonomyQuery.data, setAutonomyLocal]);
  React.useEffect(() => { if (policyQuery.data?.version) useGraphGuardStore.getState().setPolicyVersion(policyQuery.data.version); }, [policyQuery.data]);
  React.useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") { event.preventDefault(); setPaletteOpen(true); }
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, []);

  async function handleAutonomyChange(mode: AutonomyMode) {
    setSavingAutonomy(true);
    try { const saved = await setAutonomy(mode); setAutonomyLocal(saved.mode); toast.success(`Autonomy set to ${autonomyLabels[saved.mode]}`); } catch { setOffline(true); toast.error("Autonomy could not be saved"); } finally { setSavingAutonomy(false); }
  }

  const currentMode = autonomy || autonomyQuery.data?.mode || "";
  const isOffline = healthQuery.isError || health?.ok === false;
  const activeLabel = pathname === "/" ? "Investigate" : navItems.find((item) => item.href === pathname)?.label || "GraphGuard";

  function go(href: string) { setPaletteOpen(false); window.location.href = href; }

  return <div className="app-shell">
    <header className="topbar">
      <Link href="/" className="wordmark" aria-label="GraphGuard home"><span className="wordmark-mark">GG</span><span><strong>GRAPHGUARD</strong><small>SECURITY OPERATIONS</small></span></Link>
      <div className="topbar-context"><span>MISSION CONTROL</span><span className="context-slash">/</span><span>{activeLabel.toUpperCase()}</span></div>
      <div className="topbar-spacer" />
      <div className="topbar-actions">
        <span className="synthetic-badge"><CircleDot size={12} /> Synthetic data</span>
        <span className={`status-badge ${isOffline ? "offline" : ""}`}><span className="status-dot" /> {isOffline ? "API offline" : health?.falkordb ? "FalkorDB connected" : "API connected"}</span>
        {policyVersion && <span className="policy-version">Policy {policyVersion}</span>}
        <label className="autonomy-control"><span>Autonomy</span><select aria-label="Autonomy mode" value={currentMode} disabled={savingAutonomy || autonomyQuery.isLoading || !currentMode} onChange={(event) => handleAutonomyChange(event.target.value as AutonomyMode)}>{!currentMode && <option value="">Unavailable</option>}{Object.entries(autonomyLabels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
      </div>
    </header>
    {isOffline && <div className="offline-banner" role="alert"><Undo2 size={15} /><span>API offline. Live results are hidden until GraphGuard can reach FastAPI and FalkorDB.</span><button className="text-button" onClick={() => healthQuery.refetch()}>Retry connection</button></div>}
    <div className="app-body">
      <nav className="rail" aria-label="Primary navigation">{navItems.map(({ href, label, icon: Icon }) => <Link key={href} href={href} className={`rail-link ${pathname === href || (href === "/" && pathname === "/") ? "active" : ""}`} title={label}><Icon size={18} strokeWidth={1.7} /><span className="rail-label">{label}</span></Link>)}<span className="rail-bottom">{navItems.length} modules</span></nav>
      <main className="main-canvas route-fade" key={pathname}>{children}</main>
    </div>
    <button className="palette-trigger" onClick={() => setPaletteOpen(true)} title="Open command palette"><Keyboard size={14} /> <span>⌘K</span></button>
    <Command.Dialog open={paletteOpen} onOpenChange={setPaletteOpen} label="GraphGuard command palette"><div className="command-dialog"><Command.Input placeholder="Jump to a view…" autoFocus /><Command.List><Command.Empty>No matching command.</Command.Empty><Command.Group heading="Navigate">{navItems.map(({ href, label, icon: Icon }) => <Command.Item key={href} onSelect={() => go(href)}><Icon size={15} />{label}<span className="command-hint">{href}</span></Command.Item>)}</Command.Group><Command.Group heading="Actions"><Command.Item onSelect={() => { setPaletteOpen(false); toast.info("Select an alert and run an investigation first."); }}><CircleDot size={15} />Investigate selected alert</Command.Item><Command.Item onSelect={() => { setPaletteOpen(false); toast.info("Dry-run is available on a stored incident in the Actions tab."); }}><ShieldCheck size={15} />Open safe action guidance</Command.Item></Command.Group></Command.List></div></Command.Dialog>
    <Toaster theme="dark" position="bottom-right" toastOptions={{ style: { background: "#121c27", border: "1px solid #3a5062", color: "#eef5f8" } }} />
  </div>;
}
