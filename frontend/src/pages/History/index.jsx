import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import PageContainer from "../../components/layout/PageContainer";
import PageHeader from "../../components/layout/PageHeader";
import Button from "../../components/ui/Button";
import EmptyState from "../../components/ui/EmptyState";
import ErrorState from "../../components/ui/ErrorState";
import Modal from "../../components/ui/Modal";
import Select from "../../components/ui/Select";
import Skeleton from "../../components/ui/Skeleton";
import { useToast } from "../../components/ui/Toast";
import { ArrowRightIcon, ChevronDownIcon, ChevronUpIcon, ClockIcon, SearchIcon, TrashIcon } from "../../components/ui/icons";
import { useAsyncData } from "../../hooks/useAsyncData";
import { clearLectureQuestions, deleteQuestion, listHistory } from "../../services/history";
import { listLectures } from "../../services/lectures";
import { formatClock } from "../../workspace/timeline";
import { lectureLink } from "../../workspace/links";
import "./History.css";

const PAGE_SIZE = 20;
const ORDER_OPTIONS = [
  { value: "newest", label: "Newest first" },
  { value: "oldest", label: "Oldest first" },
];
const dateTime = new Intl.DateTimeFormat("en-US", { month: "short", day: "numeric", year: "numeric", hour: "numeric", minute: "2-digit" });

/** Link into the workspace that reopens this answer at its source. */
const lectureContextLink = (entry, seconds) => lectureLink(entry.lecture.id, { seconds, question: entry.id, from: "history" });

function HistoryEntry({ entry, expanded, onToggle, onDelete }) {
  const cited = (entry.sources || []).filter((source) => source.cited);
  const insufficient = entry.outcome === "insufficient_evidence";
  return (
    <li className={`history-entry ${expanded ? "is-expanded" : ""}`}>
      <button type="button" className="history-entry__summary" onClick={onToggle} aria-expanded={expanded}>
        <span className="history-entry__question">{entry.question}</span>
        {!expanded && (
          <span className={`history-entry__preview ${insufficient ? "is-insufficient" : ""}`}>
            {insufficient ? "Not enough evidence in this lecture" : entry.answer}
          </span>
        )}
        <span className="history-entry__chevron" aria-hidden="true">
          {expanded ? <ChevronUpIcon size={16} /> : <ChevronDownIcon size={16} />}
        </span>
      </button>
      <p className="history-entry__meta">
        <Link to={`/lectures/${entry.lecture.id}`} className="history-entry__lecture">
          {entry.lecture.title}
        </Link>
        <span className="mono">{dateTime.format(new Date(entry.created_at))}</span>
        {cited.length > 0 && (
          <span className="history-entry__times mono">
            {cited.map((source) => (
              <Link key={source.chunk_id} to={lectureContextLink(entry, source.start_seconds)} aria-label={`Open lecture at ${formatClock(source.start_seconds)}`}>
                <ClockIcon size={12} />
                {formatClock(source.start_seconds)}
              </Link>
            ))}
          </span>
        )}
      </p>

      {expanded && (
        <div className="history-entry__body">
          {insufficient ? (
            <div className="history-entry__insufficient" role="note">
              <p>{entry.answer}</p>
              <p className="history-entry__hint">No source was presented because the lecture didn’t contain enough evidence.</p>
            </div>
          ) : (
            <>
              <p className="history-entry__answer">{entry.answer}</p>
              {cited.length > 0 && (
                <ol className="history-sources">
                  {cited.map((source) => (
                    <li key={source.chunk_id}>
                      <Link className="history-sources__time mono" to={lectureContextLink(entry, source.start_seconds)}>
                        [{formatClock(source.start_seconds)}–{formatClock(source.end_seconds)}]
                      </Link>
                      <blockquote>{source.text}</blockquote>
                    </li>
                  ))}
                </ol>
              )}
            </>
          )}
          <div className="history-entry__actions">
            <Button as={Link} to={lectureContextLink(entry, cited[0]?.start_seconds)} variant="secondary">
              Open in lecture <ArrowRightIcon size={14} />
            </Button>
            <Button variant="tertiary" className="history-entry__delete" onClick={() => onDelete(entry)}>
              <TrashIcon size={14} /> Delete
            </Button>
          </div>
        </div>
      )}
    </li>
  );
}

export default function History() {
  const [params, setParams] = useSearchParams();
  const toast = useToast();
  const q = params.get("q") ?? "";
  const lectureId = params.get("lecture") ?? "";
  const order = params.get("order") === "oldest" ? "oldest" : "newest";
  const page = Math.max(1, Number.parseInt(params.get("page") ?? "1", 10) || 1);

  const [searchText, setSearchText] = useState(q);
  const [expandedId, setExpandedId] = useState(null);
  const [pendingDelete, setPendingDelete] = useState(null); // { kind: "one", entry } | { kind: "lecture", lecture }
  const [deleting, setDeleting] = useState(false);

  const history = useAsyncData(
    (options) => listHistory({ q, lectureId, order, limit: PAGE_SIZE, offset: (page - 1) * PAGE_SIZE }, options),
    [q, lectureId, order, page]
  );
  const lectures = useAsyncData((options) => listLectures({ status: "ready", sort: "title", limit: 100 }, options), []);

  function update(changes, { resetPage = true } = {}) {
    setParams(
      (current) => {
        const next = new URLSearchParams(current);
        Object.entries(changes).forEach(([key, value]) => (value ? next.set(key, value) : next.delete(key)));
        if (resetPage) next.delete("page");
        return next;
      },
      // Filtering keeps the reader where they are on the page.
      { replace: true, preventScrollReset: true }
    );
  }

  useEffect(() => {
    if (searchText.trim() === q) return undefined;
    const timer = setTimeout(() => update({ q: searchText.trim() }), 300);
    return () => clearTimeout(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [searchText]);

  async function confirmDelete() {
    setDeleting(true);
    try {
      if (pendingDelete.kind === "one") {
        await deleteQuestion(pendingDelete.entry.id);
        toast.show("Question deleted.");
      } else {
        await clearLectureQuestions(pendingDelete.lecture.id);
        toast.show(`Questions about "${pendingDelete.lecture.title}" were deleted.`);
      }
      setPendingDelete(null);
      const remaining = (history.data?.items.length ?? 1) - 1;
      if (pendingDelete.kind === "one" && remaining === 0 && page > 1) update({ page: String(page - 1) }, { resetPage: false });
      else history.reload();
    } catch (error) {
      toast.show(error.message || "The question couldn't be deleted.", "error");
    } finally {
      setDeleting(false);
    }
  }

  const data = history.data;
  const total = data?.total ?? 0;
  const pageCount = Math.max(1, Math.ceil(total / PAGE_SIZE));
  const filtersActive = Boolean(q || lectureId);
  const lectureOptions = [
    { value: "", label: "All lectures" },
    ...(lectures.data?.items ?? []).map((lecture) => ({ value: lecture.id, label: lecture.title })),
  ];
  const selectedLecture = (lectures.data?.items ?? []).find((lecture) => lecture.id === lectureId);

  return (
    <PageContainer className="history-page">
      <PageHeader title="Question History" description="Questions you’ve asked about your lectures, with the answers and the passages they came from." />

      <section className="history-controls" aria-label="Search and filter questions">
        <label className="history-search">
          <SearchIcon size={17} />
          <span className="visually-hidden">Search questions and answers</span>
          <input
            type="search"
            placeholder="Search questions and answers…"
            value={searchText}
            maxLength={200}
            onChange={(event) => setSearchText(event.target.value)}
          />
        </label>
        <Select
          id="history-lecture"
          label="Lecture"
          hideLabel
          options={lectureOptions}
          value={lectureId}
          onChange={(event) => update({ lecture: event.target.value })}
        />
        <Select
          id="history-order"
          label="Order"
          hideLabel
          options={ORDER_OPTIONS}
          value={order}
          onChange={(event) => update({ order: event.target.value === "newest" ? "" : event.target.value })}
        />
      </section>

      {history.status === "loading" && !data && (
        <div className="history-skeletons">
          <span className="visually-hidden" role="status">
            Loading your questions…
          </span>
          {[0, 1, 2, 3].map((key) => (
            <div key={key} className="history-skeleton" aria-hidden="true">
              <Skeleton width="45%" height={15} />
              <Skeleton width="90%" height={12} />
              <Skeleton width={260} height={11} />
            </div>
          ))}
        </div>
      )}
      {history.status === "error" && <ErrorState title="We couldn't load your question history." error={history.error} onRetry={history.reload} />}

      {data && history.status !== "error" && (
        <>
          <div className="history-summary">
            <p className="mono">
              {total} {total === 1 ? "question" : "questions"}
              {selectedLecture ? ` about ${selectedLecture.title}` : ""}
            </p>
            {selectedLecture && total > 0 && (
              <Button variant="tertiary" className="history-clear" onClick={() => setPendingDelete({ kind: "lecture", lecture: selectedLecture })}>
                <TrashIcon size={14} /> Delete all questions about this lecture
              </Button>
            )}
          </div>

          {data.items.length === 0 ? (
            filtersActive ? (
              <EmptyState
                title="No questions match"
                description="Try other words, or show questions from all lectures."
                action={
                  <Button
                    variant="secondary"
                    onClick={() => {
                      setSearchText("");
                      update({ q: "", lecture: "" });
                    }}
                  >
                    Clear filters
                  </Button>
                }
              />
            ) : (
              <EmptyState
                title="No questions yet"
                description="Ask about a lecture in its workspace, and your questions and answers will be kept here."
                action={
                  <Button as={Link} to="/library">
                    Open your library
                  </Button>
                }
              />
            )
          ) : (
            <ol className="history-list" aria-busy={history.status === "loading"}>
              {data.items.map((entry) => (
                <HistoryEntry
                  key={entry.id}
                  entry={entry}
                  expanded={entry.id === expandedId}
                  onToggle={() => setExpandedId(entry.id === expandedId ? null : entry.id)}
                  onDelete={(item) => setPendingDelete({ kind: "one", entry: item })}
                />
              ))}
            </ol>
          )}

          {pageCount > 1 && (
            <nav className="history-pagination" aria-label="Pagination">
              <Button variant="secondary" disabled={page === 1} onClick={() => update({ page: String(page - 1) }, { resetPage: false })}>
                Previous
              </Button>
              <span className="mono">
                Page {page} of {pageCount}
              </span>
              <Button variant="secondary" disabled={page >= pageCount} onClick={() => update({ page: String(page + 1) }, { resetPage: false })}>
                Next
              </Button>
            </nav>
          )}
        </>
      )}

      {pendingDelete && (
        <Modal
          title={pendingDelete.kind === "one" ? "Delete this question?" : "Delete all questions about this lecture?"}
          description={
            pendingDelete.kind === "one"
              ? `“${pendingDelete.entry.question}” and its answer will be removed from your history.`
              : `All of your questions and answers about “${pendingDelete.lecture.title}” will be removed. The lecture itself is kept.`
          }
          onClose={() => !deleting && setPendingDelete(null)}
          busy={deleting}
          actions={
            <>
              <Button variant="secondary" onClick={() => setPendingDelete(null)} disabled={deleting}>
                Cancel
              </Button>
              <Button variant="destructive" onClick={confirmDelete} disabled={deleting}>
                {deleting ? "Deleting…" : "Delete"}
              </Button>
            </>
          }
        />
      )}
    </PageContainer>
  );
}
