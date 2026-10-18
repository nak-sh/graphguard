import SectionPage from "../components/section-page";

export default function InvestigatePage() {
  return <SectionPage active="investigate" eyebrow="investigation / evidence" title="Evidence workbench" description="Inspect grounded graph evidence, compare counterfactuals, and preserve the decision context behind each proposed action." stats={[["04", "evidence queries"], ["02", "flagged signals"], ["01", "active case"]]} items={["Use the mission-control overview to select an alert and start an investigation stream.", "Evidence records are identified by stable hashes from the FastAPI graph tools.", "No action is executed from evidence inspection alone."]} />;
}
