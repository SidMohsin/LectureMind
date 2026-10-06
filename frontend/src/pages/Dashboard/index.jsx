import { useEffect, useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import PageContainer from "../../components/layout/PageContainer";
import PageHeader from "../../components/layout/PageHeader";
import Button from "../../components/ui/Button";
import Select from "../../components/ui/Select";
import Skeleton from "../../components/ui/Skeleton";
import EmptyState from "../../components/ui/EmptyState";
import ErrorState from "../../components/ui/ErrorState";
import { useToast } from "../../components/ui/Toast";
import {
  AlertIcon,
  ArrowRightIcon,
  ClockIcon,
  FileTextIcon,
  MessageIcon,
  RefreshIcon,
  SearchIcon,
} from "../../components/ui/icons";
import { useAuth } from "../../auth/AuthContext";
import { displayNameFor } from "../../auth/identity";
import { listHistory } from "../../services/history";
import { lectureLink } from "../../workspace/links";
import { SourceBadge, StatusBadge } from "../../components/lectures/LectureBadges";
import LectureMenu from "../../components/lectures/LectureMenu";
import LectureThumb from "../../components/lectures/LectureThumb";
import DeleteLectureDialog from "../../components/lectures/DeleteLectureDialog";
import RetryButton from "../../components/lectures/RetryButton";
import { useAsyncData } from "../../hooks/useAsyncData";
import { listLectures, listSubjects } from "../../services/lectures";
import { isActive, lecturePath, statusInfo } from "../../lectures/lectureStatus";
import { formatDate, formatDuration } from "../../utils/format";
import "./Dashboard.css";

const RECENT_LIMIT = 5;
// Refresh quietly while something on the page is still queued or processing.
const POLL = { intervalMs: 4000, while: (data) => data?.items.some(isActive) };
const isMac = typeof navigator !== "undefined" && /Mac|iPhone|iPad/.test(navigator.platform);

export default function Dashboard() {
  const navigate = useNavigate();
  const toast = useToast();
  const searchRef = useRef(null);
  const [search, setSearch] = useState("");
  const [subject, setSubject] = useState("");
  const [pendingDelete, setPendingDelete] = useState(null);

  const recent = useAsyncData((options) => listLectures({ subject, limit: RECENT_LIMIT }, options), [subject], { poll: POLL });
  const processing = useAsyncData((options) => listLectures({ status: "processing", limit: 3 }, options), [], {
    poll: POLL,
  });
  const failed = useAsyncData((options) => listLectures({ status: "failed", limit: 3 }, options), []);
  const subjects = useAsyncData((options) => listSubjects(options), []);
  // Overview: every lecture (for the count) and up to 100 ready ones (for hours of content).
  const all = useAsyncData((options) => listLectures({ limit: 1 }, options), []);
  const ready = useAsyncData((options) => listLectures({ status: "ready", limit: 100 }, options), []);
  const questions = useAsyncData((options) => listHistory({ limit: 3 }, options), []);
  const { user, profile } = useAuth();
  const firstName = displayNameFor(user, profile).split(" ")[0];

  useEffect(() => {
    function handleShortcut(event) {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        searchRef.current?.focus();
      }
    }
    document.addEventListener("keydown", handleShortcut);
    return () => document.removeEventListener("keydown", handleShortcut);
  }, []);

  function handleSearch(event) {
    event.preventDefault();
    const query = search.trim();
    navigate(query ? `/search?q=${encodeURIComponent(query)}` : "/search");
  }

  function reloadAll() {
    recent.reload();
    processing.reload();
    failed.reload();
    subjects.reload();
    all.reload();
    ready.reload();
    questions.reload();
  }

  function handleDeleted(lecture) {
    setPendingDelete(null);
    toast.show(`"${lecture.title}" was deleted.`);
    reloadAll();
  }

  const libraryIsEmpty = recent.status === "ready" && recent.data.total === 0 && !subject;

  return (
    <PageContainer>
      <PageHeader
        title={firstName ? `Welcome back, ${firstName}` : "Dashboard"}
        description="Pick up where you left off, or add a new lecture."
        actions={
          <>
            <form className="dashboard-search" role="search" onSubmit={handleSearch}>
              <SearchIcon size={17} />
              <label htmlFor="dashboard-search" className="visually-hidden">
                Search your lectures
              </label>
              <input
                id="dashboard-search"
                ref={searchRef}
                type="search"
                placeholder="Quick search…"
                value={search}
                onChange={(event) => setSearch(event.target.value)}
                maxLength={100}
              />
              <kbd className="mono">{isMac ? "⌘K" : "Ctrl K"}</kbd>
            </form>
          </>
        }
      />

      {!libraryIsEmpty && <Overview all={all} ready={ready} processing={processing} failed={failed} questions={questions} />}

      {processing.data?.items.map((lecture) => (
        <ProcessingCard key={lecture.id} lecture={lecture} />
      ))}
      {processing.data?.total > processing.data?.items.length && (
        <p className="dashboard-more">
          <Link to="/library?status=processing">
            View all {processing.data.total} processing lectures <ArrowRightIcon size={14} />
          </Link>
        </p>
      )}

      {failed.data?.total > 0 && (
        <section className="dashboard-section" aria-labelledby="attention-heading">
          <div className="dashboard-section__head">
            <h2 id="attention-heading" className="dashboard-section__title">
              Needs Attention
            </h2>
            {failed.data.total > failed.data.items.length && (
              <Link to="/library?status=failed" className="dashboard-link">
                View all {failed.data.total} <ArrowRightIcon size={14} />
              </Link>
            )}
          </div>
          <ul className="attention-list">
            {failed.data.items.map((lecture) => (
              <li key={lecture.id} className="attention-item">
                <AlertIcon size={18} />
                <div>
                  <Link to={lecturePath(lecture)} className="attention-item__title">
                    {lecture.title}
                  </Link>
                  <p className="attention-item__detail">
                    {lecture.job?.error_message || "Processing couldn't be completed."}
                  </p>
                </div>
                <Button as={Link} to={lecturePath(lecture)} variant="secondary">
                  View Processing Details
                </Button>
                {lecture.job?.retryable && <RetryButton lecture={lecture} onRetried={reloadAll} />}
              </li>
            ))}
          </ul>
        </section>
      )}

      <section className="dashboard-section" aria-labelledby="recent-heading">
        <div className="dashboard-section__head">
          <div>
            <h2 id="recent-heading" className="dashboard-section__title">
              Recent Lectures
            </h2>
            <p className="dashboard-section__subtitle">Your most recently added recordings.</p>
          </div>
          {!libraryIsEmpty && (
            <div className="dashboard-section__tools">
              <Select
                id="dashboard-subject"
                label="Filter by subject"
                hideLabel
                value={subject}
                onChange={(event) => setSubject(event.target.value)}
                options={[
                  { value: "", label: "All Subjects" },
                  ...(subjects.data?.subjects ?? []).map((name) => ({ value: name, label: name })),
                ]}
              />
              <Link to={subject ? `/library?subject=${encodeURIComponent(subject)}` : "/library"} className="dashboard-link">
                View All in Library <ArrowRightIcon size={14} />
              </Link>
            </div>
          )}
        </div>

        {recent.status === "error" && (
          <ErrorState title="We couldn't load your lectures." error={recent.error} onRetry={reloadAll} />
        )}
        {recent.status === "loading" && !recent.data && <TableSkeleton />}
        {libraryIsEmpty && (
          <EmptyState
            title="Your lecture library is empty"
            description="Upload your first lecture to turn it into a searchable knowledge workspace."
            action={
              <Button as={Link} to="/lectures/new">
                Add Your First Lecture
              </Button>
            }
          />
        )}
        {recent.data && recent.status !== "error" && !libraryIsEmpty && (
          <RecentTable
            data={recent.data}
            refreshing={recent.status === "loading"}
            onDelete={setPendingDelete}
          />
        )}
      </section>

      {questions.data?.items.length > 0 && <RecentQuestions data={questions.data} />}

      {pendingDelete && (
        <DeleteLectureDialog lecture={pendingDelete} onClose={() => setPendingDelete(null)} onDeleted={handleDeleted} />
      )}
    </PageContainer>
  );
}

function ProcessingCard({ lecture }) {
  const info = statusInfo(lecture.status, lecture.job);
  const eyebrow = info.waiting
    ? "Waiting"
    : info.badge === "Retrying"
      ? "Retrying"
      : isActive(lecture) && lecture.job?.status === "running"
        ? "Active processing"
        : "Queued for processing";
  return (
    <section
      className={`processing-card ${info.waiting ? "processing-card--waiting" : ""}`}
      aria-label={`Processing ${lecture.title}`}
    >
      <div className="processing-card__head">
        <span className="processing-card__icon" aria-hidden="true">
          <RefreshIcon size={18} />
        </span>
        <span className="processing-card__eyebrow mono">{eyebrow}</span>
        <h2 className="processing-card__title">{lecture.title}</h2>
        <Button as={Link} to={lecturePath(lecture)} variant="secondary" className="processing-card__action">
          View Processing Details <ArrowRightIcon size={15} />
        </Button>
      </div>
      <div className="processing-card__status">
        <span>{info.label.replace(/^Processing: /, "")}</span>
        {info.stage && (
          <span className="mono processing-card__stage">
            Stage {info.stage} of {info.totalStages}
          </span>
        )}
      </div>
      {info.stage && (
        <span
          className="processing-card__bar"
          role="progressbar"
          aria-label="Processing stage"
          aria-valuemin={0}
          aria-valuemax={info.totalStages}
          aria-valuenow={info.stage}
        >
          <span style={{ width: `${(info.stage / info.totalStages) * 100}%` }} />
        </span>
      )}
    </section>
  );
}

function RecentTable({ data, refreshing, onDelete }) {
  if (data.items.length === 0) {
    return <EmptyState title="No lectures in this subject yet" description="Choose another subject or view the whole library." />;
  }
  return (
    <div className={`recent-table ${refreshing ? "is-refreshing" : ""}`}>
      <table>
        <thead>
          <tr>
            <th scope="col">Title &amp; Subject</th>
            <th scope="col">Duration</th>
            <th scope="col" className="recent-table__optional">Source</th>
            <th scope="col" className="recent-table__optional">Date Added</th>
            <th scope="col">Processing Status</th>
            <th scope="col" className="recent-table__actions-head">
              Actions
            </th>
          </tr>
        </thead>
        <tbody>
          {data.items.map((lecture) => {
            const ready = statusInfo(lecture.status).group === "ready";
            const secondary = [lecture.subject, lecture.topic, lecture.instructor].filter(Boolean).join(" • ");
            return (
              <tr key={lecture.id} className={lecture.status === "FAILED" ? "is-failed" : undefined}>
                <td data-label="Title">
                  <div className="recent-table__lecture">
                    <LectureThumb lecture={lecture} className="recent-table__thumb" />
                    <div className="recent-table__lecture-text">
                      <Link to={lecturePath(lecture)} className="recent-table__title">
                        {lecture.title}
                      </Link>
                      {secondary && <span className="recent-table__secondary mono">{secondary}</span>}
                    </div>
                  </div>
                </td>
                <td data-label="Duration" className="mono">
                  {formatDuration(lecture.duration_seconds) ?? "—"}
                </td>
                <td data-label="Source" className="recent-table__optional">
                  <SourceBadge sourceType={lecture.source_type} />
                </td>
                <td data-label="Date added" className="recent-table__optional">{formatDate(lecture.created_at)}</td>
                <td data-label="Status">
                  <StatusBadge status={lecture.status} job={lecture.job} />
                </td>
                <td className="recent-table__actions">
                  <Button as={Link} to={lecturePath(lecture)} variant="secondary" className="recent-table__open">
                    {ready ? "Open Workspace" : "View Processing Details"}
                  </Button>
                  <LectureMenu lecture={lecture} onDelete={onDelete} />
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
      <p className="recent-table__footer mono">
        Showing {data.items.length} of {data.total} {data.total === 1 ? "lecture" : "lectures"}
      </p>
    </div>
  );
}

function TableSkeleton() {
  return (
    <div className="recent-table recent-table--skeleton" role="status" aria-label="Loading lectures">
      {[0, 1, 2].map((key) => (
        <div key={key} className="recent-table__skeleton-row">
          <span className="recent-table__skeleton-title">
            <Skeleton width="70%" height={16} />
            <Skeleton width="35%" height={11} />
          </span>
          <Skeleton width={56} height={14} />
          <Skeleton width={84} height={24} radius={999} />
          <Skeleton width={110} height={34} radius={10} />
        </div>
      ))}
    </div>
  );
}

function formatHours(seconds) {
  const hours = seconds / 3600;
  if (hours >= 10) return `${Math.round(hours)} h`;
  if (hours >= 1) return `${hours.toFixed(1)} h`;
  return `${Math.round(seconds / 60)} min`;
}

/** Real counts from the API - each tile waits for its own request. */
function Overview({ all, ready, processing, failed, questions }) {
  const readySeconds = ready.data?.items.reduce((sum, lecture) => sum + (lecture.duration_seconds || 0), 0) ?? 0;
  const partial = ready.data && ready.data.total > ready.data.items.length;
  const inProgress = (processing.data?.total ?? 0) + (failed.data?.total ?? 0);
  const tiles = [
    { icon: FileTextIcon, label: "Lectures", value: all.data?.total, loading: !all.data },
    {
      icon: ClockIcon,
      label: "Hours of lectures ready",
      value: ready.data ? `${partial ? "≥ " : ""}${formatHours(readySeconds)}` : undefined,
      loading: !ready.data,
    },
    {
      icon: RefreshIcon,
      label: failed.data?.total ? "Processing or need attention" : "Processing now",
      value: processing.data && failed.data ? inProgress : undefined,
      loading: !processing.data || !failed.data,
      to: inProgress ? `/library?status=${processing.data?.total ? "processing" : "failed"}` : undefined,
    },
    { icon: MessageIcon, label: "Questions asked", value: questions.data?.total, loading: !questions.data, to: "/history" },
  ];
  return (
    <section className="dashboard-overview" aria-label="Overview">
      {tiles.map(({ icon: Icon, label, value, loading, to }) => {
        const body = (
          <>
            <span className="dashboard-stat__icon">
              <Icon size={18} />
            </span>
            <span className="dashboard-stat__text">
              {loading ? <Skeleton width={48} height={24} /> : <span className="dashboard-stat__value">{value ?? "—"}</span>}
              <span className="dashboard-stat__label">{label}</span>
            </span>
          </>
        );
        return to ? (
          <Link key={label} to={to} className="dashboard-stat dashboard-stat--link">
            {body}
          </Link>
        ) : (
          <div key={label} className="dashboard-stat">
            {body}
          </div>
        );
      })}
    </section>
  );
}

const shortDate = new Intl.DateTimeFormat(undefined, { month: "short", day: "numeric" });

function RecentQuestions({ data }) {
  return (
    <section className="dashboard-section" aria-labelledby="questions-heading">
      <div className="dashboard-section__head">
        <div>
          <h2 id="questions-heading" className="dashboard-section__title">
            Recent Questions
          </h2>
          <p className="dashboard-section__subtitle">Reopen an answer exactly where you left it.</p>
        </div>
        <Link to="/history" className="dashboard-link">
          View All History <ArrowRightIcon size={14} />
        </Link>
      </div>
      <ul className="recent-questions">
        {data.items.map((entry) => {
          const insufficient = entry.outcome === "insufficient_evidence";
          return (
            <li key={entry.id}>
              <Link to={lectureLink(entry.lecture.id, { question: entry.id, from: "history" })} className="recent-question">
                <span className={`recent-question__icon ${insufficient ? "is-muted" : ""}`}>
                  <MessageIcon size={16} />
                </span>
                <span className="recent-question__body">
                  <span className="recent-question__text">{entry.question}</span>
                  <span className="recent-question__meta">
                    {entry.lecture.title} · {shortDate.format(new Date(entry.created_at))}
                    {insufficient && " · not answered in this lecture"}
                  </span>
                </span>
                <ArrowRightIcon size={16} />
              </Link>
            </li>
          );
        })}
      </ul>
    </section>
  );
}
