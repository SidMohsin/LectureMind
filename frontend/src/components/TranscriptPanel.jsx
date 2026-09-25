import { useState, useMemo, useRef } from 'react'
import { formatTimeRange } from '../services/format'
import EmptyState from './EmptyState'
import ErrorState from './ErrorState'
import { SkeletonBlock } from './Skeleton'

function buildDisplaySegments(segments = []) {
  if (!segments.length) return []
  const groups = []
  let current = null
  const sentenceEnd = /[.!?।]["')\\]]?$/

  function createGroup(seg) {
    return { start: seg.start, end: seg.end, text: seg.text.trim(), originalSegments: [seg] }
  }
  function addToGroup(group, seg) {
    group.end = seg.end
    group.text = `${group.text} ${seg.text.trim()}`.replace(/\s+/g, ' ').trim()
    group.originalSegments.push(seg)
  }
  function finishGroup() {
    if (current) { groups.push(current); current = null }
  }

  for (let i = 0; i < segments.length; i++) {
    const seg = segments[i]
    const text = (seg.text || '').trim()
    if (!text) continue
    if (!current) { current = createGroup(seg); continue }
    const currentDuration = current.end - current.start
    const gap = Math.max(0, seg.start - current.end)
    const proposedDuration = seg.end - current.start
    const currentEndsSentence = sentenceEnd.test(current.text)
    const segmentEndsSentence = sentenceEnd.test(text)

    if (gap >= 1.2 && currentDuration >= 12 && currentEndsSentence) {
      finishGroup(); current = createGroup(seg); continue
    }
    if (currentDuration >= 15 && currentDuration <= 22 && currentEndsSentence) {
      finishGroup(); current = createGroup(seg); continue
    }
    if (proposedDuration > 28) { finishGroup(); current = createGroup(seg); continue }
    addToGroup(current, seg)
    const newDuration = current.end - current.start
    if (newDuration >= 15 && segmentEndsSentence && newDuration <= 24) finishGroup()
  }
  finishGroup()
  return groups
}

export default function TranscriptPanel({
  transcript, loading, error, onRetry, currentTime, onSeek, searchQuery, onSearchChange,
}) {
  const [localQuery, setLocalQuery] = useState(searchQuery || '')
  const segmentRefs = useRef({})

  const query = (localQuery || '').trim().toLowerCase()

  const displaySegments = useMemo(() => {
    if (!transcript?.segments) return []
    return buildDisplaySegments(transcript.segments)
  }, [transcript])

  const activeIndex = useMemo(() => {
    if (!displaySegments.length || currentTime == null) return -1
    for (let i = 0; i < displaySegments.length; i++) {
      const seg = displaySegments[i]
      if (currentTime >= seg.start && currentTime < seg.end) return i
    }
    return -1
  }, [displaySegments, currentTime])

  function handleQueryChange(e) {
    const value = e.target.value
    setLocalQuery(value)
    if (onSearchChange) onSearchChange(value)
  }

  function highlightText(text) {
    if (!query) return text
    const lower = text.toLowerCase()
    const idx = lower.indexOf(query)
    if (idx === -1) return text
    return (
      <>
        {text.slice(0, idx)}
        <mark>{text.slice(idx, idx + query.length)}</mark>
        {text.slice(idx + query.length)}
      </>
    )
  }

  if (loading) return (
    <div className="transcript-area">
      <SkeletonBlock label="Loading transcript…" />
    </div>
  )

  if (error) return (
    <div className="transcript-area">
      <ErrorState message={error} actionLabel={onRetry ? 'Retry' : undefined} onAction={onRetry} />
    </div>
  )

  if (!transcript) return (
    <div className="transcript-area">
      <EmptyState
        title="No transcript yet"
        description="The transcript will appear here once Whisper has finished processing."
      />
    </div>
  )

  const segments = query
    ? displaySegments.filter((s) => s.text.toLowerCase().includes(query))
    : displaySegments

  return (
    <div className="transcript-area">
      <div className="transcript-search-row">
        <h3>
          Transcript
          {transcript.language && (
            <span className="muted-inline"> ({transcript.language})</span>
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
        <p className="hint">No matches for "{localQuery}".</p>
      )}

      <div className="transcript-list">
        {segments.map((seg) => {
          const origIdx = displaySegments.indexOf(seg)
          const isActive = origIdx === activeIndex
          return (
            <div
              key={origIdx}
              ref={(el) => { segmentRefs.current[origIdx] = el }}
              className={`transcript-segment ${isActive ? 'transcript-segment-active' : ''}`}
            >
              <button
                className="segment-time"
                onClick={() => onSeek && onSeek(seg.start)}
                title="Jump to this point"
              >
                {formatTimeRange(seg.start, seg.end)}
              </button>
              <span className="segment-text">{highlightText(seg.text)}</span>
            </div>
          )
        })}
      </div>
    </div>
  )
}