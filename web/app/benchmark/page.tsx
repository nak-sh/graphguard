import SectionPage from "../components/section-page";
import { BenchmarkPanel } from "../components/data-modules";

export default function BenchmarkPage() {
  return <SectionPage eyebrow="benchmark / workload" title="Benchmark board" description="Render the measured FalkorDB versus recursive SQL artifact exactly as produced by the benchmark harness, including points where SQL is competitive."><BenchmarkPanel /></SectionPage>;
}
