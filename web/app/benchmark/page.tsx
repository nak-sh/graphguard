import SectionPage from "../components/section-page";
import { BenchmarkPanel } from "../components/data-modules";

export default function BenchmarkPage() {
  return <SectionPage active="benchmark" eyebrow="benchmark / workload" title="Benchmark board" description="A neutral workspace for recording an actual run against the configured graph workload. Results are intentionally blank until a run is performed." stats={[["LIVE", "artifact"], ["SYN", "dataset"], ["P50/P95", "reported"]]} items={[]}><BenchmarkPanel /></SectionPage>;
}
