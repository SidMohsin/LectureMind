import { useEffect, useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import PageContainer from "../../components/layout/PageContainer";
import PageHeader from "../../components/layout/PageHeader";
import Button from "../../components/ui/Button";
import Select from "../../components/ui/Select";
import EmptyState from "../../components/ui/EmptyState";
import ErrorState from "../../components/ui/ErrorState";
import { useToast } from "../../components/ui/Toast";
import { AlertIcon, ArrowRightIcon, PlusIcon, RefreshIcon, SearchIcon } from "../../components/ui/icons";
import { SourceBadge, StatusBadge } from "../../components/lectures/LectureBadges";
import LectureMenu from "../../components/lectures/LectureMenu";
import DeleteLectureDialog from "../../components/lectures/DeleteLectureDialog";
import { useAsyncData } from "../../hooks/useAsyncData";
import { listLectures, listSubjects } from "../../services/lectures";
import { lecturePath, statusInfo } from "../../lectures/lectureStatus";
import { formatDate, formatDuration } from "../../utils/format";
import "./Dashboard.css";

const RECENT_LIMIT = 5;
const isMac = typeof navigator !== "undefined" && /Mac|iPhone|iPad/.test(navigator.platform);

export default function Dashboard() {
  const navigate = useNavigate();
  const toast = useToast();
  const searchRef = useRef(null);
  const [search, setSearch] = useState("");
  const [subject, setSubject] = useState("");
  const [pendingDelete, setPendingDelete] = useState(null);

  const recent = useAsyncData((options) => listLectures({ subject, limit: RECENT_LIMIT }, options), [subject]);
  const processing = useAsyncData((options) => listLectures({ status: "processing", limit: 3 }, options), []);
  const failed = useAsyncData((options) => listLectures({ status: "failed", limit: 3 }, options), []);
  const subjects = useAsyncData((options) => listSubjects(options), []);

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
    navigate(query ? `/library?q=${encodeURIComponent(query)}` : "/library");
  }

  function reloadAll() {
    recent.reload();
    processing.reload();
    failed.reload();
    subjects.reload();
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
        title="Dashboard"
        description="Manage your lectures or start a new ingestion."
        actions={
          <>
            <form className="dashboard-search" role="search" onSubmit={handleSearch}>
              <SearchIcon size={17} />
              <label htmlFor="dashboard-search" className="visually-hidden">
                Search your library
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
            <Button as={Link} to="/lectures/new">
              <PlusIcon size={16} />
              Upload Lecture
            </Button>
          </>
        }
      />

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
                  <p className="attention-item__detail">Processing couldn&apos;t be completed.</p>
                </div>
                <Button as={Link} to={lecturePath(lecture)} variant="secondary">
                  View Processing Details
                </Button>
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
                Upload Lecture
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

      {pendingDelete && (
        <DeleteLectureDialog lecture={pendingDelete} onClose={() => setPendingDelete(null)} onDeleted={handleDeleted} />
      )}
    </PageContainer>
  );
}

function ProcessingCard({ lecture }) {
  const info = statusInfo(lecture.status);
  return (
    <section className="processing-card" aria-label={`Processing ${lecture.title}`}>
      <div className="processing-card__head">
        <span className="processing-card__icon" aria-hidden="true">
          <RefreshIcon size={18} />
        </span>
        <span className="processing-card__eyebrow mono">{info.stage ? "Active processing" : "Awaiting processing"}</span>
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
            <th scope="col">Source</th>
            <th scope="col">Date Added</th>
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
                  <Link to={lecturePath(lecture)} className="recent-table__title">
                    {lecture.title}
                  </Link>
                  {secondary && <span className="recent-table__secondary mono">{secondary}</span>}
                </td>
                <td data-label="Duration" className="mono">
                  {formatDuration(lecture.duration_seconds) ?? "—"}
                </td>
                <td data-label="Source">
                  <SourceBadge sourceType={lecture.source_type} />
                </td>
                <td data-label="Date added">{formatDate(lecture.created_at)}</td>
                <td data-label="Status">
                  <StatusBadge status={lecture.status} />
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
    <div className="recent-table recent-table--skeleton" aria-hidden="true">
      {[0, 1, 2].map((key) => (
        <span key={key} />
      ))}
    </div>
  );
}
