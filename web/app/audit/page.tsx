import SectionPage from "../components/section-page";
import { AuditPanel } from "../components/data-modules";

export default function AuditPage() {
  return <SectionPage eyebrow="audit / tamper evidence" title="Audit trail" description="Review state transitions, hashes, idempotency keys, and the backend verifier without implying a result before it is returned."><AuditPanel /></SectionPage>;
}
