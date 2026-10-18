import SectionPage from "../components/section-page";
import { RedTeamPanel } from "../components/data-modules";

export default function RedTeamPage() {
  return <SectionPage active="red-team" eyebrow="red-team / counterfactuals" title="Adversarial simulation" description="Exercise decoys and policy boundaries against synthetic graph scenarios without claiming production impact." stats={[["LIVE", "scratch graphs"], ["SAFE", "simulation mode"], ["MATRIX", "last run"]]} items={[]}><RedTeamPanel /></SectionPage>;
}
