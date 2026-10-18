import SectionPage from "../components/section-page";
import { ReplayPanel } from "../components/data-modules";

export default function ReplayPage() {
  return <SectionPage active="replay" eyebrow="replay / graph timeline" title="Transaction replay" description="Follow timestamped transfer paths in order and review how a connected account reached the current alert." stats={[["LIVE", "graph source"], ["24h", "default window"], ["READ", "mode"]]} items={[]}><ReplayPanel /></SectionPage>;
}
