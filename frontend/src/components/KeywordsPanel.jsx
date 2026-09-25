import { useState } from 'react'
import EmptyState from './EmptyState'
import ErrorState from './ErrorState'
import { SkeletonBlock } from './Skeleton'

export default function KeywordsPanel({ keywords, loading, error, onRetry, onKeywordClick }) {
  const [activeKeyword, setActiveKeyword] = useState(null)

  if (loading) return (
    <div className="keywords-area">
      <SkeletonBlock label="Extracting keywords…" />
    </div>
  )

  if (error) return (
    <div className="keywords-area">
      <ErrorState message={error} actionLabel={onRetry ? 'Retry' : undefined} onAction={onRetry} />
    </div>
  )

  if (!keywords || keywords.length === 0) return (
    <div className="keywords-area">
      <EmptyState
        title="No keywords yet"
        description="Key concepts from the lecture will appear here once processing completes."
      />
    </div>
  )

  function handleClick(k) {
    setActiveKeyword(k)
    if (onKeywordClick) onKeywordClick(k)
  }

  return (
    <div className="keywords-area">
      <h3>Key concepts</h3>
      <p className="hint" style={{ marginBottom: 20 }}>
        Click a term to search for it in the transcript.
      </p>
      <div className="keyword-index">
        {keywords.map((k, i) => (
          <button
            key={i}
            className={`keyword-item ${activeKeyword === k ? 'keyword-item-active' : ''}`}
            onClick={() => handleClick(k)}
          >
            <span>{k}</span>
            <span className="keyword-arrow">→</span>
          </button>
        ))}
      </div>
    </div>
  )
}
