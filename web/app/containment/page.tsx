import SectionPage from "../components/section-page";
import { ContainmentPanel } from "../components/data-modules";

export default function ContainmentPage() {
  return <SectionPage active="containment" eyebrow="containment / action gateway" title="Containment ledger" description="Review reversible response proposals, dry-run diffs, approval state, and action-gateway receipts in one place." stats={[["LIVE", "optimizer"], ["DRY", "run required"], ["APPROVE", "current mode"]]} items={[]}><ContainmentPanel /></SectionPage>;
}
