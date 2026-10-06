import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import PageContainer from "../../components/layout/PageContainer";
import PageHeader from "../../components/layout/PageHeader";
import Button from "../../components/ui/Button";
import Select from "../../components/ui/Select";
import Skeleton from "../../components/ui/Skeleton";
import EmptyState from "../../components/ui/EmptyState";
import ErrorState from "../../components/ui/ErrorState";
import { useToast } from "../../components/ui/Toast";
import { GridIcon, ListIcon, RefreshIcon, SearchIcon } from "../../components/ui/icons";
import LectureItem from "../../components/lectures/LectureItem";
import DeleteLectureDialog from "../../components/lectures/DeleteLectureDialog";
import { useAsyncData } from "../../hooks/useAsyncData";
import { listLectures, listSubjects } from "../../services/lectures";
import { isActive } from "../../lectures/lectureStatus";
import "./Library.css";

const STATUS_OPTIONS = [
  { value: "", label: "Processing Status: All" },
  { value: "ready", label: "Ready" },
  { value: "processing", label: "Processing" },
  { value: "failed", label: "Failed" },
];

const SOURCE_OPTIONS = [
  { value: "", label: "Source Type: All" },
  { value: "video", label: "Video" },
  { value: "audio", label: "Audio" },
  { value: "url", label: "YouTube" },
];

const SORT_OPTIONS = [
  { value: "newest", label: "Recently Added (Newest first)" },
  { value: "oldest", label: "Oldest first" },
  { value: "title", label: "Title (A–Z)" },
  { value: "duration", label: "Duration (Longest first)" },
];

const PAGE_SIZES = [10, 25, 50];
// Refresh quietly while any lecture on the page is still queued or processing.
const POLL = { intervalMs: 4000, while: (data) => data?.items.some(isActive) };
const VIEW_KEY = "lecturemind.library.view";

function readView() {
  try {
    return localStorage.getItem(VIEW_KEY) === "grid" ? "grid" : "list";
  } catch {
    return "list";
  }
}

export default function Library() {
  const [params, setParams] = useSearchParams();
  const toast = useToast();

  const q = params.get("q") ?? "";
  const subject = params.get("subject") ?? "";
  const status = params.get("status") ?? "";
  const sourceType = params.get("source") ?? "";
  const sort = params.get("sort") ?? "newest";
  const pageSize = PAGE_SIZES.includes(Number(params.get("size"))) ? Number(params.get("size")) : 25;
  const page = Math.max(1, Number.parseInt(params.get("page") ?? "1", 10) || 1);

  const [searchText, setSearchText] = useState(q);
  const [view, setView] = useState(readView);
  const [pendingDelete, setPendingDelete] = useState(null);

  const lectures = useAsyncData(
    (options) =>
      listLectures({ q, subject, status, sourceType, sort, limit: pageSize, offset: (page - 1) * pageSize }, options),
    [q, subject, status, sourceType, sort, pageSize, page],
    { poll: POLL }
  );
  const subjects = useAsyncData((options) => listSubjects(options), []);

  function update(changes, { resetPage = true, keepScroll = true } = {}) {
    setParams(
      (current) => {
        const next = new URLSearchParams(current);
        Object.entries(changes).forEach(([key, value]) => (value ? next.set(key, value) : next.delete(key)));
        if (resetPage) next.delete("page");
        return next;
      },
      { replace: true, preventScrollReset: keepScroll }
    );
  }

  // Debounce typing into the URL (and therefore the request).
  useEffect(() => {
    if (searchText.trim() === q) return undefined;
    const timer = setTimeout(() => update({ q: searchText.trim() }), 300);
    return () => clearTimeout(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [searchText]);

  const outOfRange = lectures.status === "ready" && lectures.data.items.length === 0 && lectures.data.total > 0;
  useEffect(() => {
    if (outOfRange) {
      const last = Math.ceil(lectures.data.total / pageSize);
      update({ page: last > 1 ? String(last) : "" }, { resetPage: false });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [outOfRange]);

  function changeView(next) {
    setView(next);
    try {
      localStorage.setItem(VIEW_KEY, next);
    } catch {
      // Remembering the layout is a convenience only.
    }
  }

  function handleDeleted(lecture) {
    setPendingDelete(null);
    toast.show(`"${lecture.title}" was deleted.`);
    const remainingOnPage = (lectures.data?.items.length ?? 1) - 1;
    if (remainingOnPage === 0 && page > 1) update({ page: String(page - 1) }, { resetPage: false });
    else lectures.reload();
    subjects.reload();
  }

  const filtersActive = Boolean(q || subject || status || sourceType);
  const subjectOptions = [
    { value: "", label: "All Subjects" },
    ...(subjects.data?.subjects ?? []).map((name) => ({ value: name, label: name })),
    ...(subject && !(subjects.data?.subjects ?? []).includes(subject) ? [{ value: subject, label: subject }] : []),
  ];

  const data = lectures.data;
  const total = data?.total ?? 0;
  const pageCount = Math.max(1, Math.ceil(total / pageSize));
  const firstShown = total === 0 ? 0 : (page - 1) * pageSize + 1;
  const lastShown = Math.min(page * pageSize, total);

  return (
    <PageContainer>
      <PageHeader
        title="Lecture Library"
        description="All your lectures, with their transcripts, chapters and notes."
      />

      <section className="library-controls" aria-label="Search and filter lectures">
        <div className="library-controls__search-row">
          <label className="library-search">
            <SearchIcon size={18} />
            <span className="visually-hidden">Search lectures</span>
            <input
              type="search"
              placeholder="Search lectures, instructors, subjects, or tags…"
              value={searchText}
              onChange={(event) => setSearchText(event.target.value)}
              maxLength={100}
            />
          </label>
          <div className="library-view-toggle" role="group" aria-label="Layout">
            <button type="button" aria-pressed={view === "list"} aria-label="List view" onClick={() => changeView("list")}>
              <ListIcon size={18} />
            </button>
            <button type="button" aria-pressed={view === "grid"} aria-label="Grid view" onClick={() => changeView("grid")}>
              <GridIcon size={18} />
            </button>
          </div>
        </div>

        <div className="library-controls__filters">
          <Select
            id="filter-subject"
            label="Subject"
            hideLabel
            options={subjectOptions}
            value={subject}
            onChange={(event) => update({ subject: event.target.value })}
          />
          <Select
            id="filter-status"
            label="Processing status"
            hideLabel
            options={STATUS_OPTIONS}
            value={status}
            onChange={(event) => update({ status: event.target.value })}
          />
          <Select
            id="filter-source"
            label="Source type"
            hideLabel
            options={SOURCE_OPTIONS}
            value={sourceType}
            onChange={(event) => update({ source: event.target.value })}
          />
          {filtersActive && (
            <Button
              variant="tertiary"
              className="library-controls__reset"
              onClick={() => {
                setSearchText("");
                update({ q: "", subject: "", status: "", source: "" });
              }}
            >
              <RefreshIcon size={14} />
              Reset
            </Button>
          )}
          <div className="library-controls__sort">
            <Select
              id="sort"
              label="Sort by"
              hideLabel
              prefix="Sort:"
              options={SORT_OPTIONS}
              value={sort}
              onChange={(event) => update({ sort: event.target.value })}
            />
          </div>
        </div>
      </section>

      <section aria-label="Lectures" aria-busy={lectures.status === "loading"}>
        {lectures.status === "error" && (
          <ErrorState title="We couldn't load your lectures." error={lectures.error} onRetry={lectures.reload} />
        )}

        {lectures.status === "loading" && !data && <LectureSkeletons layout={view} />}

        {data && lectures.status !== "error" && data.items.length === 0 && !outOfRange && (
          filtersActive ? (
            <EmptyState
              title="No lectures match these filters"
              description="Try a different search term or clear the filters."
              action={
                <Button
                  variant="secondary"
                  onClick={() => {
                    setSearchText("");
                    update({ q: "", subject: "", status: "", source: "" });
                  }}
                >
                  Clear filters
                </Button>
              }
            />
          ) : (
            <EmptyState
              title="Your lecture library is empty"
              description="Upload your first lecture to turn it into a searchable knowledge workspace."
              action={
                <Button as={Link} to="/lectures/new">
                  Add Your First Lecture
                </Button>
              }
            />
          )
        )}

        {data && lectures.status !== "error" && data.items.length > 0 && (
          <>
            <div className={`library-list library-list--${view} ${lectures.status === "loading" ? "is-refreshing" : ""}`}>
              {data.items.map((lecture) => (
                <LectureItem
                  key={lecture.id}
                  lecture={lecture}
                  layout={view}
                  onDelete={setPendingDelete}
                  onRetried={lectures.reload}
                />
              ))}
            </div>

            <footer className="library-pagination">
              <div className="library-pagination__size">
                <Select
                  id="page-size"
                  label="Rows per page"
                  hideLabel
                  prefix="Rows per page:"
                  size="sm"
                  placement="up"
                  options={PAGE_SIZES.map((size) => ({ value: String(size), label: String(size) }))}
                  value={String(pageSize)}
                  onChange={(event) => update({ size: event.target.value === "25" ? "" : event.target.value })}
                />
                <span className="mono library-pagination__count">
                  Showing {firstShown} – {lastShown} of {total} {total === 1 ? "lecture" : "lectures"}
                </span>
              </div>
              {pageCount > 1 && (
                <nav className="library-pagination__pages" aria-label="Pagination">
                  <button
                    type="button"
                    disabled={page === 1}
                    aria-label="Previous page"
                    onClick={() => update({ page: String(page - 1) }, { resetPage: false, keepScroll: false })}
                  >
                    ‹
                  </button>
                  {Array.from({ length: pageCount }, (_, index) => index + 1).map((number) => (
                    <button
                      key={number}
                      type="button"
                      aria-current={number === page ? "page" : undefined}
                      onClick={() => update({ page: number === 1 ? "" : String(number) }, { resetPage: false, keepScroll: false })}
                    >
                      {number}
                    </button>
                  ))}
                  <button
                    type="button"
                    disabled={page === pageCount}
                    aria-label="Next page"
                    onClick={() => update({ page: String(page + 1) }, { resetPage: false, keepScroll: false })}
                  >
                    ›
                  </button>
                </nav>
              )}
            </footer>
          </>
        )}
      </section>

      {pendingDelete && (
        <DeleteLectureDialog
          lecture={pendingDelete}
          onClose={() => setPendingDelete(null)}
          onDeleted={handleDeleted}
        />
      )}
    </PageContainer>
  );
}

function LectureSkeletons({ layout }) {
  return (
    <div className={`library-list library-list--${layout}`}>
      {[0, 1, 2].map((key) => (
        <div key={key} className="lecture-skeleton" aria-hidden="true">
          <Skeleton className="lecture-skeleton__tile" height="auto" radius={10} />
          <span className="lecture-skeleton__lines">
            <Skeleton width="30%" height={12} />
            <Skeleton width="75%" height={18} />
            <Skeleton width="45%" height={12} />
          </span>
        </div>
      ))}
      <span className="visually-hidden" role="status">
        Loading lectures…
      </span>
    </div>
  );
}
