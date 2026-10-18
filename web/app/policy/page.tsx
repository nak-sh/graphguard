import SectionPage from "../components/section-page";
import { PolicyPanel } from "../components/data-modules";

export default function PolicyPage() {
  return <SectionPage active="policy" eyebrow="policy / autonomy" title="Policy controls" description="Make autonomy explicit, inspect the action tier, and keep policy decisions visible to the operator." stats={[["V2", "policy schema"], ["4", "autonomy modes"], ["LIVE", "cached evidence"]]} items={[]}><PolicyPanel /></SectionPage>;
}
