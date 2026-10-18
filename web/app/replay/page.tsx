import SectionPage from "../components/section-page";
import { ReplayPanel } from "../components/data-modules";

export default function ReplayPage() {
  return <SectionPage eyebrow="replay / graph timeline" title="Transaction replay" description="Follow the timestamped transfer frames returned for the selected entity and identify the exact cycle-closing moment."><ReplayPanel /></SectionPage>;
}
