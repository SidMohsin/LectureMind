import { useParams } from "react-router-dom";
import PagePlaceholder from "../../components/layout/PagePlaceholder";

export default function Workspace() {
  const { id } = useParams();
  return (
    <PagePlaceholder
      title="Lecture Workspace"
      description={`The flagship workspace for lecture "${id}" — media player, synchronized transcript, lecture intelligence and grounded Q&A — is implemented in Phase 6.`}
      phase="Phase 6 — Lecture Workspace + Grounded Q&A"
    />
  );
}
