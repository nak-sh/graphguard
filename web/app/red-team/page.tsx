import SectionPage from "../components/section-page";
import { RedTeamPanel } from "../components/data-modules";

export default function RedTeamPage() {
  return <SectionPage eyebrow="red-team / counterfactuals" title="Adversarial simulation" description="Inspect isolated synthetic evasion variants, including honest misses and the backend's suggested policy knob."><RedTeamPanel /></SectionPage>;
}
