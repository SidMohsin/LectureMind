import { useParams } from "react-router-dom";
import PagePlaceholder from "../../components/layout/PagePlaceholder";

export default function Processing() {
  const { id } = useParams();
  return (
    <PagePlaceholder
      title="Processing Details"
      description={`The processing lifecycle view for lecture "${id}" (stages, progress, retry) is implemented in Phase 4.`}
      phase="Phase 4 — Lecture Ingestion + Processing"
    />
  );
}
