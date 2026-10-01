import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import PageContainer from "../../components/layout/PageContainer";
import PageHeader from "../../components/layout/PageHeader";
import { StatusBadge } from "../../components/lectures/LectureBadges";
import { AlertIcon, ArrowRightIcon, ClockIcon, RefreshIcon, SearchIcon } from "../../components/ui/icons";
import { useAsyncData } from "../../hooks/useAsyncData";
import { listLectures } from "../../services/lectures";
import { searchContent } from "../../services/search";
import { formatDate } from "../../utils/format";
import { formatClock, highlightParts } from "../../workspace/timeline";
import { lectureLink } from "../../workspace/links";
import "./Search.css";

const MIN_LENGTH = 3;
const LECTURE_PREVIEW = 5;

/** Words of the query worth highlighting in a passage (no tiny/common words). */
function highlightTerms(query) {
  const stop = new Set(["what", "when", "where", "which", "does", "with", "that", "this", "from", "about", "there", "their", "have", "into", "they", "lecture"]);
  return [...new Set(query.toLowerCase().match(/[\p{L}\p{N}]{4,}/gu) || [])].filter((word) => !stop.has(word)).slice(0, 6);
}

function Highlighted({ text, terms }) {
  let parts = [{ text, match: false }];
  terms.forEach((term) => {
    parts = parts.flatMap((part) => (part.match ? [part] : highlightParts(part.text, term)));
  });
  return parts.map((part, index) => (part.match ? <mark key={index}>{part.text}</mark> : <span key={index}>{part.text}</span>));
}

function SectionStatus({ state, onRetry, loading, empty }) {
  if (state.status === "loading") {
    return (
      <p className="search-status" role="status">
        <span className="search-status__spinner" aria-hidden="true" /> {loading}
      </p>
    );
  }
  if (state.status === "error") {
    return (
      <div className="search-error" role="alert">
        <AlertIcon size={16} />
        <p>{state.error?.message || "Search failed."}</p>
        <button type="button" onClick={onRetry}>
          <RefreshIcon size={14} /> Retry
        </button>
      </div>
    );
  }
  return empty ? <p className="search-empty">{empty}</p> : null;
}

function LectureResults({ query, state }) {
  const items = state.data?.items ?? [];
  const total = state.data?.total ?? 0;
  return (
    <section className="search-section" aria-labelledby="search-lectures">
      <div className="search-section__head">
        <h2 id="search-lectures">Lectures</h2>
        <p className="search-section__hint">Matching title, subject, topic, instructor or tags</p>
      </div>
      <SectionStatus
        state={state}
        onRetry={state.reload}
        loading="Searching your library…"
        empty={state.status === "ready" && !items.length && "No lecture titles or details match."}
      />
      {state.status === "ready" && items.length > 0 && (
        <>
          <ul className="search-lectures">
            {items.map((lecture) => (
              <li key={lecture.id}>
                <Link to={`/lectures/${lecture.id}`} className="search-lecture">
                  <span className="search-lecture__title">{lecture.title}</span>
                  <span className="search-lecture__meta mono">
                    {[
                      [lecture.subject, lecture.topic].filter(Boolean).join(" · "),
                      lecture.instructor,
                      lecture.lecture_date && formatDate(lecture.lecture_date),
                    ]
                      .filter(Boolean)
                      .join("  •  ")}
                  </span>
                  <StatusBadge status={lecture.status} job={lecture.job} />
                </Link>
              </li>
            ))}
          </ul>
          {total > items.length && (
            <Link className="search-more" to={`/library?q=${encodeURIComponent(query)}`}>
              View all {total} in Library <ArrowRightIcon size={14} />
            </Link>
          )}
        </>
      )}
    </section>
  );
}

function PassageResult({ result, terms }) {
  const [expanded, setExpanded] = useState(false);
  const { lecture } = result;
  return (
    <li className="passage">
      <div className="passage__head">
        <Link to={`/lectures/${lecture.id}`} className="passage__lecture">
          {lecture.title}
        </Link>
        {(lecture.subject || lecture.topic) && (
          <span className="passage__subject mono">{[lecture.subject, lecture.topic].filter(Boolean).join(" · ")}</span>
        )}
      </div>
      <p className="passage__time mono">
        <ClockIcon size={13} /> {formatClock(result.start_seconds)} – {formatClock(result.end_seconds)}
      </p>
      <blockquote className={`passage__text ${expanded ? "is-expanded" : ""}`}>
        <Highlighted text={result.text} terms={terms} />
      </blockquote>
      <div className="passage__actions">
        <Link className="passage__open" to={lectureLink(lecture.id, { seconds: result.start_seconds, from: "search" })}>
          Open at {formatClock(result.start_seconds)} <ArrowRightIcon size={14} />
        </Link>
        <button type="button" className="passage__toggle" aria-expanded={expanded} onClick={() => setExpanded(!expanded)}>
          {expanded ? "Show less" : "Show full passage"}
        </button>
      </div>
    </li>
  );
}

function PassageResults({ query, state }) {
  const results = state.data?.results ?? [];
  const terms = highlightTerms(query);
  return (
    <section className="search-section" aria-labelledby="search-passages">
      <div className="search-section__head">
        <h2 id="search-passages">Passages in your lectures</h2>
        <p className="search-section__hint">Matched by meaning in the transcripts of your ready lectures</p>
      </div>
      <SectionStatus
        state={state}
        onRetry={state.reload}
        loading="Finding passages that discuss this…"
        empty={
          state.status === "ready" &&
          !results.length &&
          "No passage in your lectures is a close enough match. Try describing the concept differently."
        }
      />
      {state.status === "ready" && results.length > 0 && (
        <ol className="passages">
          {results.map((result) => (
            <PassageResult key={result.chunk_id} result={result} terms={terms} />
          ))}
        </ol>
      )}
    </section>
  );
}

export default function Search() {
  const [params, setParams] = useSearchParams();
  const query = (params.get("q") ?? "").trim();
  const [text, setText] = useState(query);
  const [touched, setTouched] = useState(false);
  const valid = query.length >= MIN_LENGTH;

  useEffect(() => setText(query), [query]);

  const lectures = useAsyncData(
    (options) => (valid ? listLectures({ q: query, limit: LECTURE_PREVIEW }, options) : Promise.resolve(null)),
    [query, valid]
  );
  const passages = useAsyncData(
    (options) => (valid ? searchContent(query, {}, options) : Promise.resolve(null)),
    [query, valid]
  );

  const submit = (event) => {
    event.preventDefault();
    setTouched(true);
    const next = text.trim();
    if (next.length < MIN_LENGTH) return;
    setParams(next ? { q: next } : {});
  };

  const tooShort = touched && text.trim().length < MIN_LENGTH;

  return (
    <PageContainer className="search-page">
      <PageHeader title="Search" description="Find lectures by their details, or the passages where a topic is explained." />

      <form className="search-form" role="search" onSubmit={submit} noValidate>
        <label className="search-input">
          <SearchIcon size={18} />
          <span className="visually-hidden">Search lectures, topics and concepts</span>
          <input
            type="search"
            placeholder="Search lectures, topics, concepts..."
            value={text}
            maxLength={300}
            onChange={(event) => setText(event.target.value)}
            aria-invalid={tooShort || undefined}
            aria-describedby={tooShort ? "search-validation" : undefined}
          />
        </label>
        <button type="submit" className="search-submit">
          Search
        </button>
      </form>
      {tooShort && (
        <p id="search-validation" className="search-validation" role="alert">
          Enter at least {MIN_LENGTH} characters.
        </p>
      )}

      {!valid ? (
        <div className="search-intro">
          <p>Search works two ways at once:</p>
          <ul>
            <li>
              <strong>Lectures</strong> — by title, subject, topic, instructor or tags.
            </li>
            <li>
              <strong>Passages</strong> — describe a concept or ask a question, and LectureMind finds where your lectures explain
              it, with the timestamp.
            </li>
          </ul>
        </div>
      ) : (
        <div className="search-results">
          <PassageResults query={query} state={passages} />
          <LectureResults query={query} state={lectures} />
        </div>
      )}
    </PageContainer>
  );
}
