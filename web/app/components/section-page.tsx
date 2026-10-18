import Link from "next/link";
import type { ReactNode } from "react";

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

type SectionPageProps = {
  active: string;
  eyebrow: string;
  title: string;
  description: string;
  stats: Array<[string, string]>;
  items: string[];
  children?: ReactNode;
};

export default function SectionPage({ active, eyebrow, title, description, stats, items, children }: SectionPageProps) {
  return (
    <div className="app-shell">
      <header className="topbar">
        <Link href="/" className="wordmark" aria-label="GraphGuard home"><span className="wordmark-mark" aria-hidden="true">GG</span><span><strong>GRAPHGUARD</strong><span>SECURITY OPERATIONS / V2</span></span></Link>
        <div className="topbar-context"><span>MISSION CONTROL</span><span className="context-slash">/</span><span>{active.toUpperCase()}</span></div><div className="topbar-spacer" />
        <div className="topbar-actions"><span className="synthetic-badge"><span className="status-dot" /> SYNTHETIC DATA</span><span className="status-badge"><span className="status-dot" /> FASTAPI</span><label className="autonomy-control"><span>Autonomy</span><select aria-label="Autonomy mode"><option>Approve</option><option>Recommend</option><option>Observe</option></select></label></div>
      </header>
      <div className="app-body">
        <nav className="rail" aria-label="Primary navigation">{navItems.map((item) => <Link key={item.href} href={item.href} className={`rail-link${item.href === `/${active}` || (active === "overview" && item.href === "/") ? " active" : ""}`}><span className="rail-icon" aria-hidden="true">{item.icon}</span><span className="rail-label">{item.label}</span></Link>)}<span className="rail-bottom">OPERATIONS / 07</span></nav>
        <main className="main-canvas"><div className="page-heading"><div><div className="eyebrow">/ {eyebrow}</div><h1>{title}</h1><p className="subheading">{description}</p></div><div className="heading-meta"><span className="live">● READY</span><span>synthetic workspace</span></div></div>
          <section className="route-card"><h2>{title} <span style={{ color: "var(--dim)", font: "400 11px var(--mono)" }}>/ module</span></h2><p>{description}</p><div className="route-grid">{stats.map(([value, label]) => <div className="route-stat" key={label}><strong>{value}</strong><span>{label}</span></div>)}</div>{children || <ul className="route-list">{items.map((item) => <li key={item}><strong>•</strong>&nbsp;&nbsp;{item}</li>)}</ul>}</section>
        </main>
      </div>
    </div>
  );
}
