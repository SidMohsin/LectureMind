import { useMemo, useState } from "react";
import { citationStart, chunkTimeMap, findChapterIndex, formatClock } from "../../workspace/timeline";
import { readableParagraphs } from "../../workspace/text";
import "./IntelligencePanel.css";

/** A lecture timestamp that seeks the player. */
export function Timestamp({ seconds, onSeek, prefix = "" }) {
  if (seconds === null || seconds === undefined) return null;
  const label = formatClock(seconds);
  return (
    <button type="button" className="timestamp mono" onClick={() => onSeek(seconds)} aria-label={`Play from ${label}`}>
      {prefix}
      {label}
    </button>
  );
}

const TABS = [
  { id: "summary", label: "Summary" },
  { id: "chapters", label: "Chapters" },
  { id: "concepts", label: "Concepts" },
  { id: "topics", label: "Topics" },
];

function Section({ title, count, children }) {
  return (
    <section className="intel-section">
      <h3 className="intel-section__title">
        {title}
        {count !== undefined && <span className="intel-section__count mono">{count}</span>}
      </h3>
      {children}
    </section>
  );
}

function Empty({ children }) {
  return <p className="intel-empty">{children}</p>;
}

export function ChapterList({ chapters, currentTime, onSeek }) {
  const active = findChapterIndex(chapters, currentTime);
  if (!chapters.length) return <Empty>No chapters were generated for this lecture.</Empty>;
  return (
    <ol className="chapter-list">
      {chapters.map((chapter, index) => (
        <li key={chapter.sequence} className={index === active ? "is-active" : ""}>
          <button
            type="button"
            className="chapter-list__item"
            onClick={() => onSeek(chapter.start_seconds)}
            aria-current={index === active ? "true" : undefined}
          >
            <span className="chapter-list__number mono">{String(index + 1).padStart(2, "0")}</span>
            <span className="chapter-list__body">
              <span className="chapter-list__title">{chapter.title}</span>
              {chapter.description && <span className="chapter-list__description">{chapter.description}</span>}
            </span>
            <span className="chapter-list__time mono">
              {formatClock(chapter.start_seconds)} – {formatClock(chapter.end_seconds)}
            </span>
          </button>
        </li>
      ))}
    </ol>
  );
}

/**
 * Lecture intelligence produced during processing (Phase 5), displayed as stored.
 * Items cite transcript chunks; the earliest cited chunk gives each item's timestamp.
 */
export default function IntelligencePanel({ intelligence, chapters, chunks, currentTime, onSeek }) {
  const [tab, setTab] = useState("summary");
  const chunkMap = useMemo(() => chunkTimeMap(chunks), [chunks]);
  const startOf = (item) => citationStart(item.chunks, chunkMap);

  if (!intelligence) {
    return (
      <section className="intel" aria-label="Lecture intelligence">
        <h2 className="intel__heading">Lecture intelligence</h2>
        <Empty>Lecture intelligence isn’t available for this lecture yet.</Empty>
      </section>
    );
  }

  const paragraphs = readableParagraphs(intelligence.summary);

  return (
    <section className="intel" aria-label="Lecture intelligence">
      <div className="intel__header">
        <h2 className="intel__heading">Lecture intelligence</h2>
        <p className="intel__counts mono">
          {chapters.length} chapters · {intelligence.key_concepts.length} concepts
        </p>
      </div>

      <div className="intel__tabs" role="tablist" aria-label="Lecture intelligence sections">
        {TABS.map((item) => (
          <button
            key={item.id}
            type="button"
            role="tab"
            id={`intel-tab-${item.id}`}
            aria-selected={tab === item.id}
            aria-controls={`intel-panel-${item.id}`}
            className="intel__tab"
            onClick={() => setTab(item.id)}
          >
            {item.label}
          </button>
        ))}
      </div>

      <div className="intel__body" role="tabpanel" id={`intel-panel-${tab}`} aria-labelledby={`intel-tab-${tab}`}>
        {tab === "summary" && (
          <>
            <Section title="Summary">
              <div className="intel-summary">
                {paragraphs.map((text, index) => (
                  <p key={index}>{text}</p>
                ))}
              </div>
            </Section>
            <Section title="Important points" count={intelligence.important_points.length}>
              {intelligence.important_points.length ? (
                <ul className="intel-points">
                  {intelligence.important_points.map((item, index) => (
                    <li key={index}>
                      <span>{item.point}</span>
                      <Timestamp seconds={startOf(item)} onSeek={onSeek} />
                    </li>
                  ))}
                </ul>
              ) : (
                <Empty>No important points were identified.</Empty>
              )}
            </Section>
          </>
        )}

        {tab === "chapters" && <ChapterList chapters={chapters} currentTime={currentTime} onSeek={onSeek} />}

        {tab === "concepts" && (
          <>
            <Section title="Key concepts" count={intelligence.key_concepts.length}>
              {intelligence.key_concepts.length ? (
                <ul className="knowledge-list">
                  {intelligence.key_concepts.map((item, index) => (
                    <li key={index} className="knowledge">
                      <div className="knowledge__head">
                        <span className="knowledge__kind">Key concept</span>
                        <Timestamp seconds={startOf(item)} onSeek={onSeek} prefix="@ " />
                      </div>
                      <p className="knowledge__name">{item.name}</p>
                      {item.explanation && <p className="knowledge__text">{item.explanation}</p>}
                    </li>
                  ))}
                </ul>
              ) : (
                <Empty>No key concepts were identified.</Empty>
              )}
            </Section>
            <Section title="Definitions" count={intelligence.definitions.length}>
              {intelligence.definitions.length ? (
                <ul className="knowledge-list">
                  {intelligence.definitions.map((item, index) => (
                    <li key={index} className="knowledge knowledge--definition">
                      <div className="knowledge__head">
                        <span className="knowledge__kind">Definition</span>
                        <Timestamp seconds={startOf(item)} onSeek={onSeek} prefix="@ " />
                      </div>
                      <p className="knowledge__name">{item.term}</p>
                      <p className="knowledge__text">{item.definition}</p>
                    </li>
                  ))}
                </ul>
              ) : (
                <Empty>The lecturer didn’t give explicit definitions.</Empty>
              )}
            </Section>
          </>
        )}

        {tab === "topics" && (
          <>
            <Section title="Topics" count={intelligence.topics.length}>
              {intelligence.topics.length ? (
                <ul className="topic-list">
                  {intelligence.topics.map((item, index) => (
                    <li key={index}>
                      <div className="topic-list__head">
                        <span className="topic-list__name">{item.name}</span>
                        <Timestamp seconds={startOf(item)} onSeek={onSeek} />
                      </div>
                      {item.subtopics?.length > 0 && (
                        <ul className="topic-list__subtopics">
                          {item.subtopics.map((subtopic) => (
                            <li key={subtopic}>{subtopic}</li>
                          ))}
                        </ul>
                      )}
                    </li>
                  ))}
                </ul>
              ) : (
                <Empty>No topics were identified.</Empty>
              )}
            </Section>
            <Section title="Examples" count={intelligence.examples.length}>
              {intelligence.examples.length ? (
                <ul className="intel-points">
                  {intelligence.examples.map((item, index) => (
                    <li key={index}>
                      <span>{item.description}</span>
                      <Timestamp seconds={startOf(item)} onSeek={onSeek} />
                    </li>
                  ))}
                </ul>
              ) : (
                <Empty>No worked examples were identified in this lecture.</Empty>
              )}
            </Section>
            <Section title="Keywords" count={intelligence.keywords.length}>
              {intelligence.keywords.length ? (
                <ul className="keyword-list">
                  {intelligence.keywords.map((keyword) => (
                    <li key={keyword} className="mono">
                      {keyword}
                    </li>
                  ))}
                </ul>
              ) : (
                <Empty>No keywords were identified.</Empty>
              )}
            </Section>
          </>
        )}
      </div>
    </section>
  );
}
