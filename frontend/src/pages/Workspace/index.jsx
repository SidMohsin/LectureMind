import { useCallback, useEffect, useRef, useState } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";
import PageContainer from "../../components/layout/PageContainer";
import Button from "../../components/ui/Button";
import EmptyState from "../../components/ui/EmptyState";
import ErrorState from "../../components/ui/ErrorState";
import Skeleton, { SkeletonText } from "../../components/ui/Skeleton";
import { useToast } from "../../components/ui/Toast";
import { CloseIcon, ExternalIcon, LayersIcon, MessageIcon, PlayIcon, TrashIcon } from "../../components/ui/icons";
import { SourceBadge, StatusBadge } from "../../components/lectures/LectureBadges";
import DeleteLectureDialog from "../../components/lectures/DeleteLectureDialog";
import { useAsyncData } from "../../hooks/useAsyncData";
import { getWorkspace } from "../../services/workspace";
import { statusInfo } from "../../lectures/lectureStatus";
import { thumbnailUrl } from "../../lectures/thumbnails";
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
        <Button variant="secondary" onClick={onDelete} aria-label="Delete lecture" className="workspace-header__delete">
          <TrashIcon size={15} />
          <span className="workspace-header__delete-label">Delete</span>
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

/** Where the user came from (search result or question history) and the position it points to. */
function ContextBar({ origin, seconds, onPlay, onDismiss }) {
  const label = origin === "history" ? "Opened from your question history" : "Opened from search";
  return (
    <div className="workspace-context" role="status">
      <p>
        {label}
        {seconds !== null && (
          <>
            {" "}
            — passage at <span className="mono">{formatClock(seconds)}</span>
          </>
        )}
      </p>
      {seconds !== null && (
        <button type="button" className="workspace-context__play" onClick={onPlay}>
          <PlayIcon size={12} /> Play from {formatClock(seconds)}
        </button>
      )}
      <button type="button" className="workspace-context__dismiss" onClick={onDismiss} aria-label="Dismiss">
        <CloseIcon size={14} />
      </button>
    </div>
  );
}

/** Loading placeholder shaped like the workspace, so nothing jumps when it arrives. */
function WorkspaceSkeleton() {
  return (
    <PageContainer className="workspace-page">
      <span className="visually-hidden" role="status">
        Loading lecture…
      </span>
      <div className="workspace-header workspace-header--skeleton" aria-hidden="true">
        <div className="workspace-header__main">
          <Skeleton width={180} height={22} radius={999} />
          <Skeleton width="min(640px, 90%)" height={34} style={{ marginTop: 14 }} />
          <Skeleton width={220} height={14} style={{ marginTop: 12 }} />
        </div>
      </div>
      <div className="workspace-layout" aria-hidden="true">
        <div className="workspace-main">
          <div className="workspace-skeleton-card">
            <Skeleton height={150} radius={12} />
            <Skeleton height={10} radius={999} style={{ marginTop: 18 }} />
            <div className="workspace-skeleton-row">
              <Skeleton width={40} height={40} radius={10} />
              <Skeleton width={120} height={14} />
            </div>
          </div>
          <div className="workspace-skeleton-card">
            <Skeleton height={36} radius={10} />
            {[0, 1, 2, 3, 4, 5].map((key) => (
              <div key={key} className="workspace-skeleton-row">
                <Skeleton width={52} height={20} radius={6} />
                <Skeleton width={`${60 + ((key * 13) % 35)}%`} height={14} />
              </div>
            ))}
          </div>
        </div>
        <div className="workspace-side">
          <div className="workspace-skeleton-card">
            <Skeleton height={38} radius={10} />
            <Skeleton height={44} radius={10} style={{ marginTop: 16 }} />
            <div style={{ marginTop: 20 }}>
              <SkeletonText lines={4} />
            </div>
          </div>
        </div>
      </div>
    </PageContainer>
  );
}

/** Right column: one place for Q&A and the generated notes, switched by tabs. */
function SidePanel({ tab, onTab, qa, notes }) {
  const tabs = [
    { id: "ask", label: "Ask", Icon: MessageIcon },
    { id: "notes", label: "Lecture notes", Icon: LayersIcon },
  ];
  return (
    <div className="workspace-panel">
      <div className="workspace-panel__switch" role="tablist" aria-label="Workspace panel">
        {tabs.map(({ id, label, Icon }) => (
          <button
            key={id}
            type="button"
            role="tab"
            id={`side-tab-${id}`}
            aria-selected={tab === id}
            aria-controls={`side-panel-${id}`}
            className="workspace-panel__tab"
            onClick={() => onTab(id)}
          >
            <Icon size={15} />
            {label}
          </button>
        ))}
      </div>
      <div id="side-panel-ask" role="tabpanel" aria-labelledby="side-tab-ask" hidden={tab !== "ask"}>
        {qa}
      </div>
      <div id="side-panel-notes" role="tabpanel" aria-labelledby="side-tab-notes" hidden={tab !== "notes"}>
        {notes}
      </div>
    </div>
  );
}

function readSeconds(value) {
  const seconds = Number.parseFloat(value ?? "");
  return Number.isFinite(seconds) && seconds >= 0 ? seconds : null;
}

export default function Workspace() {
  const { id } = useParams();
  const [searchParams] = useSearchParams();
  const startAt = readSeconds(searchParams.get("t"));
  const focusQuestion = searchParams.get("question");
  const origin = searchParams.get("from");
  const [showContext, setShowContext] = useState(Boolean(origin));
  const navigate = useNavigate();
  const toast = useToast();
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [currentTime, setCurrentTime] = useState(0);
  const [sideTab, setSideTab] = useState("ask");
  const playerRef = useRef(null);
  const workspace = useAsyncData((options) => getWorkspace(id, options), [id]);

  const seek = useCallback((seconds) => {
    setCurrentTime(seconds);
    playerRef.current?.seek(seconds, { play: true });
  }, []);

  // Opened at a position (from a search result or a history source): show it there without autoplay.
  const isReady = workspace.data && statusInfo(workspace.data.lecture.status).group === "ready";
  useEffect(() => {
    if (!isReady || startAt === null) return;
    setCurrentTime(startAt);
    playerRef.current?.seek(startAt);
  }, [isReady, startAt]);

  if (workspace.status === "loading" && !workspace.data) return <WorkspaceSkeleton />;

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
        <>
        {showContext && (origin === "search" || origin === "history") && (
          <ContextBar
            origin={origin}
            seconds={startAt}
            onPlay={() => playerRef.current?.seek(startAt, { play: true })}
            onDismiss={() => setShowContext(false)}
          />
        )}
        <div className="workspace-layout">
          <div className="workspace-main">
            <div className="workspace-area workspace-area--player">
              <MediaPlayer
                ref={playerRef}
                lectureId={lecture.id}
                chapters={chapters}
                fallbackDuration={lecture.duration_seconds}
                onTimeUpdate={setCurrentTime}
                artwork={thumbnailUrl(lecture)}
                title={lecture.title}
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
            <div className="workspace-area workspace-area--side">
              <SidePanel
                tab={sideTab}
                onTab={setSideTab}
                qa={<QuestionPanel lectureId={lecture.id} onSeek={seek} focusQuestionId={focusQuestion} />}
                notes={
                  <IntelligencePanel
                    intelligence={intelligence}
                    chapters={chapters}
                    chunks={chunks}
                    currentTime={currentTime}
                    onSeek={seek}
                  />
                }
              />
            </div>
          </div>
        </div>
        </>
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
