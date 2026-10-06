import { memo, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { ChevronDownIcon, ChevronUpIcon, SearchIcon } from "../../components/ui/icons";
import { findActiveIndex, formatClock, highlightParts, searchSegments } from "../../workspace/timeline";
import "./TranscriptPanel.css";

const Segment = memo(function Segment({ segment, active, query, current, onSeek }) {
  const parts = highlightParts(segment.text, query);
  return (
    <li
      className={`transcript__segment ${active ? "is-active" : ""} ${current ? "is-match" : ""}`}
      data-index={segment.sequence}
      aria-current={active ? "true" : undefined}
    >
      <button
        type="button"
        className="transcript__time mono"
        onClick={() => onSeek(segment.start)}
        aria-label={`Play from ${formatClock(segment.start)}`}
      >
        {formatClock(segment.start)}
        {active && <span className="transcript__playing">Playing</span>}
      </button>
      <p className="transcript__text" onClick={() => onSeek(segment.start)}>
        {parts.map((part, index) =>
          part.match ? <mark key={index}>{part.text}</mark> : <span key={index}>{part.text}</span>
        )}
      </p>
    </li>
  );
});

const COMPACT_QUERY = "(max-width: 767px)";

/** True on phone-sized screens; follows rotation and window resizing. */
function useCompactScreen() {
  const query = typeof window !== "undefined" && window.matchMedia ? window.matchMedia(COMPACT_QUERY) : null;
  const [compact, setCompact] = useState(() => Boolean(query?.matches));
  useEffect(() => {
    if (!query) return undefined;
    const update = () => setCompact(query.matches);
    query.addEventListener?.("change", update);
    return () => query.removeEventListener?.("change", update);
  }, [query]);
  return compact;
}

/**
 * The timestamped transcript, as stored by processing (never rewritten here).
 * The active segment follows playback; clicking a segment seeks the player.
 * Following pauses when the reader scrolls themselves and can be resumed.
 * On phones it starts collapsed to the line being spoken, so the page stays short.
 */
export default function TranscriptPanel({ transcript, currentTime, onSeek }) {
  const segments = useMemo(() => transcript?.segments || [], [transcript]);
  const listRef = useRef(null);
  const [query, setQuery] = useState("");
  const [matchCursor, setMatchCursor] = useState(0);
  const [follow, setFollow] = useState(true);
  const compact = useCompactScreen();
  const [collapsed, setCollapsed] = useState(compact);
  useEffect(() => setCollapsed(compact), [compact]);

  const activeIndex = findActiveIndex(segments, currentTime);
  const matches = useMemo(() => searchSegments(segments, query), [segments, query]);
  const currentMatch = matches.length ? matches[Math.min(matchCursor, matches.length - 1)] : -1;

  // Scrolls only the transcript list (never the page) to keep a row in view.
  const scrollToIndex = useCallback((index) => {
    const list = listRef.current;
    const row = list?.children[index];
    if (!list || !row) return;
    const offset = row.getBoundingClientRect().top - list.getBoundingClientRect().top;
    const top = list.scrollTop + offset - list.clientHeight / 3;
    list.scrollTo?.({ top: Math.max(0, top), behavior: "smooth" });
  }, []);

  useEffect(() => {
    if (follow && activeIndex >= 0 && !query.trim()) scrollToIndex(activeIndex);
  }, [activeIndex, follow, query, scrollToIndex, collapsed]);

  useEffect(() => {
    if (currentMatch >= 0) scrollToIndex(currentMatch);
  }, [currentMatch, scrollToIndex]);

  const stepMatch = (delta) => {
    if (!matches.length) return;
    setMatchCursor((cursor) => (cursor + delta + matches.length) % matches.length);
  };

  const rows = useMemo(
    () =>
      segments.map((segment, index) => (
        <Segment
          key={segment.sequence}
          segment={segment}
          active={index === activeIndex}
          current={index === currentMatch}
          query={query}
          onSeek={onSeek}
        />
      )),
    [segments, activeIndex, currentMatch, query, onSeek]
  );

  if (!segments.length) {
    return (
      <section className="transcript" aria-label="Transcript">
        <p className="transcript__empty">No transcript is available for this lecture.</p>
      </section>
    );
  }

  const stopFollowing = () => follow && setFollow(false);
  const nowSegment = segments[Math.max(0, activeIndex)];
  const count = `${segments.length} segments${transcript.language ? ` · ${transcript.language.toUpperCase()}` : ""}`;

  return (
    <section className={`transcript ${collapsed ? "transcript--collapsed" : ""}`} aria-label="Transcript">
      {compact && (
        <div className="transcript__head">
          <div>
            <h2 className="transcript__heading">Transcript</h2>
            <p className="transcript__count mono">{count}</p>
          </div>
          <button
            type="button"
            className="transcript__toggle"
            aria-expanded={!collapsed}
            aria-controls="transcript-body"
            onClick={() => setCollapsed((value) => !value)}
          >
            {collapsed ? "Show transcript" : "Hide"}
            {collapsed ? <ChevronDownIcon size={16} /> : <ChevronUpIcon size={16} />}
          </button>
        </div>
      )}

      {collapsed && nowSegment && (
        <button type="button" className="transcript__now" onClick={() => setCollapsed(false)}>
          <span className="transcript__now-label mono">
            {activeIndex >= 0 ? "Now playing" : "Starts"} · {formatClock(nowSegment.start)}
          </span>
          <span className="transcript__now-text">{nowSegment.text}</span>
        </button>
      )}

      <div id="transcript-body" className="transcript__body" hidden={collapsed}>
      <div className="transcript__toolbar">
        <label className="transcript__search">
          <SearchIcon size={16} />
          <span className="visually-hidden">Find in transcript</span>
          <input
            type="search"
            placeholder="Find in transcript…"
            value={query}
            onChange={(event) => {
              setQuery(event.target.value);
              setMatchCursor(0);
            }}
            onKeyDown={(event) => {
              if (event.key === "Enter") {
                event.preventDefault();
                stepMatch(event.shiftKey ? -1 : 1);
              }
            }}
          />
        </label>
        {query.trim().length >= 2 && (
          <div className="transcript__matches">
            <span className="mono" role="status">
              {matches.length ? `${Math.min(matchCursor, matches.length - 1) + 1} of ${matches.length}` : "No matches"}
            </span>
            <button type="button" onClick={() => stepMatch(-1)} disabled={!matches.length} aria-label="Previous match">
              <ChevronUpIcon size={16} />
            </button>
            <button type="button" onClick={() => stepMatch(1)} disabled={!matches.length} aria-label="Next match">
              <ChevronDownIcon size={16} />
            </button>
          </div>
        )}
        <button
          type="button"
          className="transcript__follow"
          aria-pressed={follow}
          onClick={() => {
            setFollow(!follow);
            if (!follow && activeIndex >= 0) scrollToIndex(activeIndex);
          }}
        >
          Follow playback: <strong>{follow ? "On" : "Off"}</strong>
        </button>
      </div>

      <ol className="transcript__list" ref={listRef} onWheel={stopFollowing} onTouchMove={stopFollowing}>
        {rows}
      </ol>
      {!compact && <p className="transcript__footer mono">{count}</p>}
      </div>
    </section>
  );
}
