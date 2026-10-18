import SectionPage from "../components/section-page";
import { AuditPanel } from "../components/data-modules";

export default function AuditPage() {
  return <SectionPage active="audit" eyebrow="audit / tamper evidence" title="Audit trail" description="Verify append-only action history and keep the actor, idempotency key, and state transition available for review." stats={[["LIVE", "chain status"], ["SHA-256", "event hash"], ["VERIFY", "control"]]} items={[]}><AuditPanel /></SectionPage>;
}
