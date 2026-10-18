import SectionPage from "../components/section-page";
import { PolicyPanel } from "../components/data-modules";

export default function PolicyPage() {
  return <SectionPage eyebrow="policy / autonomy" title="Policy controls" description="Tune a sandbox copy of the active backend policy, evaluate stored scenarios, and surface decoy regressions before saving a new version."><PolicyPanel /></SectionPage>;
}
