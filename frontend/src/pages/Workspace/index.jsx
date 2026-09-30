import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import PageContainer from "../../components/layout/PageContainer";
import Button from "../../components/ui/Button";
import EmptyState from "../../components/ui/EmptyState";
import ErrorState from "../../components/ui/ErrorState";
import FullPageLoader from "../../components/feedback/FullPageLoader";
import { useToast } from "../../components/ui/Toast";
import { TrashIcon } from "../../components/ui/icons";
import { SourceBadge, StatusBadge } from "../../components/lectures/LectureBadges";
import DeleteLectureDialog from "../../components/lectures/DeleteLectureDialog";
import { useAsyncData } from "../../hooks/useAsyncData";
import { getLecture } from "../../services/lectures";
import { statusInfo } from "../../lectures/lectureStatus";
import { formatDate, formatDuration } from "../../utils/format";
import "./Workspace.css";

export default function Workspace() {
  const { id } = useParams();
  const navigate = useNavigate();
  const toast = useToast();
  const [confirmDelete, setConfirmDelete] = useState(false);
  const lecture = useAsyncData((options) => getLecture(id, options), [id]);

  if (lecture.status === "loading" && !lecture.data) return <FullPageLoader label="Loading lecture…" />;

  if (lecture.status === "error") {
    const missing = lecture.error.status === 404 || lecture.error.status === 422;
    return (
      <PageContainer>
        {missing ? (
          <EmptyState
            title="Lecture not found"
            description="This lecture doesn't exist, was deleted, or isn't in your library."
            action={
              <Button as={Link} to="/library">
                Back to Library
              </Button>
            }
          />
        ) : (
          <ErrorState title="We couldn't load this lecture." error={lecture.error} onRetry={lecture.reload} />
        )}
      </PageContainer>
    );
  }

  const data = lecture.data;
  const ready = statusInfo(data.status).group === "ready";
  const meta = [
    data.instructor,
    data.lecture_date && `Recorded ${formatDate(data.lecture_date)}`,
    formatDuration(data.duration_seconds) && `${formatDuration(data.duration_seconds)} total`,
  ].filter(Boolean);

  return (
    <PageContainer>
      <header className="workspace-header">
        <div className="workspace-header__main">
          <div className="workspace-header__badges">
            <StatusBadge status={data.status} />
            <SourceBadge sourceType={data.source_type} />
            {data.subject && <span className="workspace-header__subject mono">{[data.subject, data.topic].filter(Boolean).join(" · ")}</span>}
          </div>
          <h1 className="workspace-header__title">{data.title}</h1>
          {meta.length > 0 && (
            <p className="workspace-header__meta">
              {meta.map((part) => (
                <span key={part}>{part}</span>
              ))}
            </p>
          )}
        </div>
        <Button variant="secondary" onClick={() => setConfirmDelete(true)}>
          <TrashIcon size={15} />
          Delete
        </Button>
      </header>

      <EmptyState
        title={ready ? "The lecture workspace is coming next" : "This lecture is still being processed"}
        description={
          ready
            ? "The media player, synchronized transcript, lecture intelligence and grounded Q&A for this lecture are the next part of LectureMind being built."
            : "Once processing finishes, this is where you'll study the lecture."
        }
        action={
          !ready && (
            <Button as={Link} to={`/lectures/${data.id}/processing`} variant="secondary">
              View Processing Details
            </Button>
          )
        }
      />

      {confirmDelete && (
        <DeleteLectureDialog
          lecture={data}
          onClose={() => setConfirmDelete(false)}
          onDeleted={(deleted) => {
            toast.show(`"${deleted.title}" was deleted.`);
            navigate("/library", { replace: true });
          }}
        />
      )}
    </PageContainer>
  );
}
