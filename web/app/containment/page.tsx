import SectionPage from "../components/section-page";
import { ContainmentPanel } from "../components/data-modules";

export default function ContainmentPage() {
  return <SectionPage eyebrow="containment / action gateway" title="Containment ledger" description="Compare backend-generated containment options and their estimated collateral trade-offs before opening the safe action workflow."><ContainmentPanel /></SectionPage>;
}
