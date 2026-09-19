import { useState, useMemo, useRef, useEffect } from 'react'
import { formatTimeRange } from '../services/format'
import EmptyState from './EmptyState'
import ErrorState from './ErrorState'
import { SkeletonBlock } from './Skeleton'

/*
  Convert Whisper's small timestamp segments into larger,
  readable transcript blocks.

  Rules:
  - Prefer 15-20 seconds
  - Do not unnecessarily break sentences
  - Allow a block to go slightly beyond 20 seconds
    when needed to finish a sentence
  - Hard limit around 28 seconds
  - Respect natural pauses between segments
*/
function buildDisplaySegments(segments = []) {
  if (!segments.length) return []

  const groups = []
  let current = null

  const sentenceEnd = /[.!?।]["')\]]?$/
  const strongPause = /[.!?।]["')\]]?\s*$/

  function createGroup(seg) {
    return {
      start: seg.start,
      end: seg.end,
      text: seg.text.trim(),
      originalSegments: [seg],
    }
  }

  function addToGroup(group, seg) {
    group.end = seg.end
    group.text = `${group.text} ${seg.text.trim()}`.replace(/\s+/g, ' ').trim()
    group.originalSegments.push(seg)
  }

  function finishGroup() {
    if (current) {
      groups.push(current)
      current = null
    }
  }

  for (let i = 0; i < segments.length; i++) {
    const seg = segments[i]
    const text = (seg.text || '').trim()

    if (!text) continue

    if (!current) {
      current = createGroup(seg)
      continue
    }

    const currentDuration = current.end - current.start
    const gap = Math.max(0, seg.start - current.end)
    const proposedDuration = seg.end - current.start

    const currentEndsSentence = sentenceEnd.test(current.text)
    const segmentEndsSentence = sentenceEnd.test(text)

    /*
      If there is a noticeable pause after a complete sentence,
      start a new logical block.
    */
    if (
      gap >= 1.2 &&
      currentDuration >= 12 &&
      currentEndsSentence
    ) {
      finishGroup()
      current = createGroup(seg)
      continue
    }

    /*
      Once we have reached the target range, prefer ending
      at a sentence boundary.
    */
    if (
      currentDuration >= 15 &&
      currentDuration <= 22 &&
      currentEndsSentence
    ) {
      finishGroup()
      current = createGroup(seg)
      continue
    }

    /*
      If adding this segment would make the block too large,
      finish the current block before adding it.
    */
    if (proposedDuration > 28) {
      finishGroup()
      current = createGroup(seg)
      continue
    }

    addToGroup(current, seg)

    /*
      If the block has reached a reasonable size and this
      segment itself completes a sentence, close it.
    */
    const newDuration = current.end - current.start

    if (
      newDuration >= 15 &&
      segmentEndsSentence &&
      newDuration <= 24
    ) {
      finishGroup()
    }
  }

  finishGroup()

  return groups
}

export default function TranscriptPanel({
  transcript,
  loading,
  error,
  onRetry,
  currentTime,
  onSeek,
  searchQuery,
  onSearchChange,
}) {
  const [localQuery, setLocalQuery] = useState(searchQuery || '')
  const segmentRefs = useRef({})
  // const activeIndexRef = useRef(-1)

  useEffect(() => {
    setLocalQuery(searchQuery || '')
  }, [searchQuery])

  const query = (localQuery || '').trim().toLowerCase()

  /*
    Keep the original Whisper segments untouched.
    Only create larger blocks for displaying them in the UI.
  */
  const displaySegments = useMemo(() => {
    if (!transcript?.segments) return []
    return buildDisplaySegments(transcript.segments)
  }, [transcript])

  /*
    Find the logical display block currently playing.
  */
  const activeIndex = useMemo(() => {
    if (
      !displaySegments.length ||
      currentTime === undefined ||
      currentTime === null
    ) {
      return -1
    }

    for (let i = 0; i < displaySegments.length; i++) {
      const seg = displaySegments[i]

      if (
        currentTime >= seg.start &&
        currentTime < seg.end
      ) {
        return i
      }
    }

    return -1
  }, [displaySegments, currentTime])

  /*
    Auto-scroll only inside the transcript list.
    It does NOT change the active tab.
  */
  // useEffect(() => {
  //   if (
  //     activeIndex >= 0 &&
  //     activeIndex !== activeIndexRef.current
  //   ) {
  //     activeIndexRef.current = activeIndex

  //     const el = segmentRefs.current[activeIndex]

  //     if (el) {
  //       el.scrollIntoView({
  //         behavior: 'smooth',
  //         block: 'center',
  //       })
  //     }
  //   }
  // }, [activeIndex])

  function handleQueryChange(e) {
    const value = e.target.value

    setLocalQuery(value)

    if (onSearchChange) {
      onSearchChange(value)
    }
  }

  function highlightText(text) {
    if (!query) return text

    const lowerText = text.toLowerCase()
    const index = lowerText.indexOf(query)

    if (index === -1) return text

    return (
      <>
        {text.slice(0, index)}
        <mark>
          {text.slice(index, index + query.length)}
        </mark>
        {text.slice(index + query.length)}
      </>
    )
  }

  if (loading) {
    return (
      <div className="card">
        <h3>Transcript</h3>
        <SkeletonBlock label="Loading transcript…" />
      </div>
    )
  }

  if (error) {
    return (
      <div className="card">
        <h3>Transcript</h3>

        <ErrorState
          message={error}
          actionLabel={onRetry ? 'Retry' : undefined}
          onAction={onRetry}
        />
      </div>
    )
  }

  if (!transcript) {
    return (
      <div className="card">
        <EmptyState
          title="No transcript available"
          description="The transcript will appear here once Whisper has finished processing this lecture."
        />
      </div>
    )
  }

  /*
    Search is performed on the larger logical display blocks.
  */
  const segments = query
    ? displaySegments.filter((segment) =>
        segment.text.toLowerCase().includes(query)
      )
    : displaySegments

  return (
    <div className="card">
      <div className="panel-header-row">
        <h3>
          Transcript{' '}
          {transcript.language ? (
            <span className="muted-inline">
              ({transcript.language})
            </span>
          ) : (
            ''
          )}
        </h3>

        <input
          type="search"
          className="panel-search-input"
          placeholder="Search transcript…"
          value={localQuery}
          onChange={handleQueryChange}
          aria-label="Search transcript"
        />
      </div>

      {query && segments.length === 0 && (
        <p className="hint">
          No matches for "{localQuery}".
        </p>
      )}

      <div className="transcript-list">
        {segments.map((seg) => {
          const originalIndex =
            displaySegments.indexOf(seg)

          const isActive =
            originalIndex === activeIndex

          return (
            <div
              key={originalIndex}
              ref={(element) => {
                segmentRefs.current[originalIndex] = element
              }}
              className={`transcript-segment ${
                isActive
                  ? 'transcript-segment-active'
                  : ''
              }`}
            >
              <button
                className="segment-time"
                onClick={() =>
                  onSeek && onSeek(seg.start)
                }
                title="Jump to this point in the lecture"
              >
                {formatTimeRange(seg.start, seg.end)}
              </button>

              <span className="segment-text">
                {highlightText(seg.text)}
              </span>
            </div>
          )
        })}
      </div>
    </div>
  )
}