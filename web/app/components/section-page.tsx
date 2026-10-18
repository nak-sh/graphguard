import type { ReactNode } from "react";

type SectionPageProps = { eyebrow: string; title: string; description: string; children: ReactNode };

export default function SectionPage({ eyebrow, title, description, children }: SectionPageProps) {
  return <div className="page-stack"><div className="page-heading"><div><div className="eyebrow">/ {eyebrow}</div><h1>{title}</h1><p className="subheading">{description}</p></div><div className="heading-meta"><span className="lead-note">Synthetic findings are leads, not proof.</span></div></div>{children}</div>;
}
