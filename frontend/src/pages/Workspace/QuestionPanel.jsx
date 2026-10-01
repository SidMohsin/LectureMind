import { useEffect, useState } from "react";
import { askQuestion, listQuestions } from "../../services/workspace";
import { deleteQuestion } from "../../services/history";
import Modal from "../../components/ui/Modal";
import Button from "../../components/ui/Button";
import { AlertIcon, ChevronDownIcon, ChevronUpIcon, ClockIcon, RefreshIcon, SendIcon, TrashIcon } from "../../components/ui/icons";
import { formatClock } from "../../workspace/timeline";
import "./QuestionPanel.css";

const MAX_LENGTH = 500;
const dateTime = new Intl.DateTimeFormat("en-US", { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" });

function SourceList({ sources, onSeek }) {
  const [open, setOpen] = useState(false);
  if (!sources.length) return null;
  return (
    <div className="qa-sources">
      <p className="qa-sources__label mono">Lecture sources</p>
      <ul className="qa-sources__chips">
        {sources.map((source) => (
          <li key={source.chunk_id}>
            <button
              type="button"
              className="qa-source"
              onClick={() => onSeek(source.start_seconds)}
              aria-label={`Play source from ${formatClock(source.start_seconds)}`}
            >
              <ClockIcon size={14} />
              <span className="mono">{formatClock(source.start_seconds)}</span>
            </button>
          </li>
        ))}
      </ul>
      <button type="button" className="qa-evidence-toggle" aria-expanded={open} onClick={() => setOpen(!open)}>
        {open ? <ChevronUpIcon size={14} /> : <ChevronDownIcon size={14} />}
        {open ? "Hide" : "View"} source passages ({sources.length})
      </button>
      {open && (
        <ol className="qa-evidence">
          {sources.map((source) => (
            <li key={source.chunk_id}>
              <button type="button" className="qa-evidence__time mono" onClick={() => onSeek(source.start_seconds)}>
                [{formatClock(source.start_seconds)}–{formatClock(source.end_seconds)}]
              </button>
              <blockquote>{source.text}</blockquote>
            </li>
          ))}
        </ol>
      )}
    </div>
  );
}

function Entry({ entry, expanded, onToggle, onSeek, onDelete }) {
  const cited = (entry.sources || []).filter((source) => source.cited);
  const insufficient = entry.outcome === "insufficient_evidence";
  const when = dateTime.format(new Date(entry.created_at));

  if (!expanded) {
    return (
      <li className="qa-history__item">
        <button type="button" className="qa-history__button" onClick={onToggle} aria-expanded="false">
          <span className="qa-history__question">{entry.question}</span>
          <span className="qa-history__preview">{insufficient ? "Not enough evidence in this lecture" : entry.answer}</span>
          <span className="qa-history__meta mono">
            {when}
            {cited.length > 0 && ` · ${cited.map((source) => formatClock(source.start_seconds)).join(", ")}`}
          </span>
        </button>
      </li>
    );
  }

  return (
    <li className={`qa-entry ${insufficient ? "qa-entry--insufficient" : ""}`} data-question-id={entry.id}>
      <div className="qa-entry__question">
        <span className="qa-entry__label mono">Question</span>
        <p>{entry.question}</p>
        <button type="button" className="qa-entry__collapse" onClick={onToggle} aria-expanded="true" aria-label="Collapse answer">
          <ChevronUpIcon size={16} />
        </button>
      </div>
      {insufficient ? (
        <div className="qa-entry__insufficient" role="note">
          <p>{entry.answer}</p>
          <p className="qa-entry__hint">Try asking about a concept covered in the lecture.</p>
        </div>
      ) : (
        <>
          <p className="qa-entry__answer">{entry.answer}</p>
          <SourceList sources={cited} onSeek={onSeek} />
        </>
      )}
      <div className="qa-entry__footer">
        <p className="qa-entry__meta mono">
          {when} · answered in {(entry.latency_ms / 1000).toFixed(1)} s
        </p>
        <button type="button" className="qa-entry__delete" onClick={() => onDelete(entry)} aria-label="Delete this question">
          <TrashIcon size={14} />
        </button>
      </div>
    </li>
  );
}

/**
 * Grounded Q&A for this lecture. Answers come only from retrieved lecture passages;
 * every source is a real transcript passage the server retrieved, and clicking it
 * seeks the player. Questions and answers are kept as this lecture's history.
 */
export default function QuestionPanel({ lectureId, onSeek, focusQuestionId }) {
  const [entries, setEntries] = useState([]);
  const [historyState, setHistoryState] = useState("loading");
  const [expandedId, setExpandedId] = useState(null);
  const [question, setQuestion] = useState("");
  const [pending, setPending] = useState(null);
  const [failed, setFailed] = useState(null);
  const [pendingDelete, setPendingDelete] = useState(null);
  const [deleting, setDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState(null);

  const loadHistory = () => {
    setHistoryState("loading");
    listQuestions(lectureId)
      .then((data) => {
        setEntries(data.items);
        // Opened from question history: show that answer; otherwise the latest.
        const focused = data.items.find((item) => item.id === focusQuestionId);
        setExpandedId(focused?.id ?? data.items[0]?.id ?? null);
        setHistoryState("ready");
      })
      .catch(() => setHistoryState("error"));
  };

  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(loadHistory, [lectureId]);

  const submit = async (text) => {
    const value = text.trim();
    if (value.length < 3 || pending) return;
    setPending(value);
    setFailed(null);
    try {
      const entry = await askQuestion(lectureId, value);
      setEntries((current) => [entry, ...current]);
      setExpandedId(entry.id);
      setQuestion("");
    } catch (error) {
      setFailed({ question: value, message: error.message });
    } finally {
      setPending(null);
    }
  };

  useEffect(() => {
    if (!focusQuestionId || expandedId !== focusQuestionId) return;
    document.querySelector(`[data-question-id="${focusQuestionId}"]`)?.scrollIntoView?.({ block: "nearest" });
  }, [focusQuestionId, expandedId]);

  const confirmDelete = async () => {
    setDeleting(true);
    setDeleteError(null);
    try {
      await deleteQuestion(pendingDelete.id);
      setEntries((current) => current.filter((item) => item.id !== pendingDelete.id));
      setPendingDelete(null);
    } catch (error) {
      setDeleteError(error.message || "The question couldn't be deleted.");
    } finally {
      setDeleting(false);
    }
  };

  const tooShort = question.trim().length < 3;

  return (
    <section className="qa" aria-label="Ask about this lecture">
      <h2 className="qa__heading">Ask about this lecture</h2>
      <form
        className="qa__form"
        onSubmit={(event) => {
          event.preventDefault();
          submit(question);
        }}
      >
        <label htmlFor="qa-question" className="visually-hidden">
          Your question
        </label>
        <input
          id="qa-question"
          type="text"
          placeholder="Ask something about this lecture..."
          value={question}
          maxLength={MAX_LENGTH}
          onChange={(event) => setQuestion(event.target.value)}
          disabled={Boolean(pending)}
          autoComplete="off"
        />
        <button type="submit" className="qa__ask" disabled={tooShort || Boolean(pending)}>
          Ask <SendIcon size={14} />
        </button>
      </form>
      <p className="qa__note">Answers use only this lecture’s transcript and link to the passages they rely on.</p>

      {pending && (
        <div className="qa-pending" role="status">
          <span className="qa-pending__spinner" aria-hidden="true" />
          <div>
            <p className="qa-pending__question">{pending}</p>
            <p className="qa-pending__text">Finding the relevant parts of the lecture and preparing an answer…</p>
          </div>
        </div>
      )}

      {failed && !pending && (
        <div className="qa-error" role="alert">
          <AlertIcon size={16} />
          <p>{failed.message || "The answer couldn't be generated."}</p>
          <button type="button" onClick={() => submit(failed.question)}>
            <RefreshIcon size={14} /> Retry
          </button>
        </div>
      )}

      {historyState === "loading" && <p className="qa__status">Loading earlier questions…</p>}
      {historyState === "error" && (
        <div className="qa-error" role="alert">
          <AlertIcon size={16} />
          <p>Earlier questions couldn’t be loaded.</p>
          <button type="button" onClick={loadHistory}>
            <RefreshIcon size={14} /> Retry
          </button>
        </div>
      )}
      {historyState === "ready" && entries.length === 0 && !pending && (
        <p className="qa__status">No questions yet. Ask about anything covered in this lecture.</p>
      )}

      {entries.length > 0 && (
        <>
          {entries.length > 1 && <p className="qa__history-label mono">Questions about this lecture ({entries.length})</p>}
          <ol className="qa-history">
            {entries.map((entry) => (
              <Entry
                key={entry.id}
                entry={entry}
                expanded={entry.id === expandedId}
                onToggle={() => setExpandedId(entry.id === expandedId ? null : entry.id)}
                onSeek={onSeek}
                onDelete={setPendingDelete}
              />
            ))}
          </ol>
        </>
      )}

      {pendingDelete && (
        <Modal
          title="Delete this question?"
          description={`“${pendingDelete.question}” and its answer will be removed from your history.`}
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
        >
          {deleteError && (
            <p className="qa-delete-error" role="alert">
              {deleteError}
            </p>
          )}
        </Modal>
      )}
    </section>
  );
}
