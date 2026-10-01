import { useCallback, useRef, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import PageContainer from "../../components/layout/PageContainer";
import Button from "../../components/ui/Button";
import EmptyState from "../../components/ui/EmptyState";
import ErrorState from "../../components/ui/ErrorState";
import FullPageLoader from "../../components/feedback/FullPageLoader";
import { useToast } from "../../components/ui/Toast";
import { ExternalIcon, TrashIcon } from "../../components/ui/icons";
import { SourceBadge, StatusBadge } from "../../components/lectures/LectureBadges";
import DeleteLectureDialog from "../../components/lectures/DeleteLectureDialog";
import { useAsyncData } from "../../hooks/useAsyncData";
import { getWorkspace } from "../../services/workspace";
import { statusInfo } from "../../lectures/lectureStatus";
import { formatDate, formatDuration } from "../../utils/format";
import { findChapterIndex, formatClock } from "../../workspace/timeline";
import MediaPlayer from "./MediaPlayer";
import TranscriptPanel from "./TranscriptPanel";
import IntelligencePanel from "./IntelligencePanel";
import QuestionPanel from "./QuestionPanel";
import "./Workspace.css";

function WorkspaceHeader({ lecture, onDelete }) {
  const meta = [
    lecture.instructor,
    lecture.lecture_date && `Recorded ${formatDate(lecture.lecture_date)}`,
    formatDuration(lecture.duration_seconds) && `${formatDuration(lecture.duration_seconds)} total`,
  ].filter(Boolean);
  return (
    <header className="workspace-header">
      <div className="workspace-header__main">
        <div className="workspace-header__badges">
          <StatusBadge status={lecture.status} job={lecture.job} />
          <SourceBadge sourceType={lecture.source_type} />
          {lecture.subject && (
            <span className="workspace-header__subject mono">{[lecture.subject, lecture.topic].filter(Boolean).join(" · ")}</span>
          )}
        </div>
        <h1 className="workspace-header__title">{lecture.title}</h1>
        {meta.length > 0 && (
          <p className="workspace-header__meta">
            {meta.map((part) => (
              <span key={part}>{part}</span>
            ))}
          </p>
        )}
      </div>
      <div className="workspace-header__actions">
        {lecture.source_type === "url" && lecture.source_url && (
          <Button as="a" variant="secondary" href={lecture.source_url} target="_blank" rel="noopener noreferrer">
            <ExternalIcon size={15} />
            Original source
          </Button>
        )}
        <Button as={Link} variant="secondary" to={`/lectures/${lecture.id}/processing`}>
          Processing details
        </Button>
        <Button variant="secondary" onClick={onDelete}>
          <TrashIcon size={15} />
          Delete
        </Button>
      </div>
    </header>
  );
}

/** Compact chapter navigation under the player on small screens. */
function ChapterStrip({ chapters, currentTime, onSeek }) {
  if (!chapters.length) return null;
  const active = findChapterIndex(chapters, currentTime);
  return (
    <nav className="chapter-strip" aria-label="Chapters">
      <ol>
        {chapters.map((chapter, index) => (
          <li key={chapter.sequence}>
            <button
              type="button"
              className={index === active ? "is-active" : ""}
              aria-current={index === active ? "true" : undefined}
              aria-label={`${chapter.title}, from ${formatClock(chapter.start_seconds)}`}
              onClick={() => onSeek(chapter.start_seconds)}
            >
              <span className="mono">{formatClock(chapter.start_seconds)}</span>
              {chapter.title}
            </button>
          </li>
        ))}
      </ol>
    </nav>
  );
}

export default function Workspace() {
  const { id } = useParams();
  const navigate = useNavigate();
  const toast = useToast();
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [currentTime, setCurrentTime] = useState(0);
  const playerRef = useRef(null);
  const workspace = useAsyncData((options) => getWorkspace(id, options), [id]);

  const seek = useCallback((seconds) => {
    setCurrentTime(seconds);
    playerRef.current?.seek(seconds, { play: true });
  }, []);

  if (workspace.status === "loading" && !workspace.data) return <FullPageLoader label="Loading lecture…" />;

  if (workspace.status === "error") {
    const missing = workspace.error.status === 404 || workspace.error.status === 422;
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
          <ErrorState title="We couldn't load this lecture." error={workspace.error} onRetry={workspace.reload} />
        )}
      </PageContainer>
    );
  }

  const { lecture, transcript, chapters, intelligence, chunks } = workspace.data;
  const ready = statusInfo(lecture.status).group === "ready";

  return (
    <PageContainer className="workspace-page">
      <WorkspaceHeader lecture={lecture} onDelete={() => setConfirmDelete(true)} />

      {!ready ? (
        <EmptyState
          title="This lecture is still being processed"
          description="Once processing finishes, this is where you'll study the lecture: player, synchronized transcript, lecture intelligence and questions."
          action={
            <Button as={Link} to={`/lectures/${lecture.id}/processing`} variant="secondary">
              View Processing Details
            </Button>
          }
        />
      ) : (
        <div className="workspace-layout">
          <div className="workspace-main">
            <div className="workspace-area workspace-area--player">
              <MediaPlayer
                ref={playerRef}
                lectureId={lecture.id}
                chapters={chapters}
                fallbackDuration={lecture.duration_seconds}
                onTimeUpdate={setCurrentTime}
              />
            </div>
            <div className="workspace-area workspace-area--chapters">
              <ChapterStrip chapters={chapters} currentTime={currentTime} onSeek={seek} />
            </div>
            <div className="workspace-area workspace-area--transcript">
              <TranscriptPanel transcript={transcript} currentTime={currentTime} onSeek={seek} />
            </div>
          </div>
          <div className="workspace-side">
            <div className="workspace-area workspace-area--qa">
              <QuestionPanel lectureId={lecture.id} onSeek={seek} />
            </div>
            <div className="workspace-area workspace-area--intel">
              <IntelligencePanel
                intelligence={intelligence}
                chapters={chapters}
                chunks={chunks}
                currentTime={currentTime}
                onSeek={seek}
              />
            </div>
          </div>
        </div>
      )}

      {confirmDelete && (
        <DeleteLectureDialog
          lecture={lecture}
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
