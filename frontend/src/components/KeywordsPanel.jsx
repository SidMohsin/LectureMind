import { useState } from 'react'
import EmptyState from './EmptyState'
import ErrorState from './ErrorState'
import { SkeletonBlock } from './Skeleton'

export default function KeywordsPanel({ keywords, loading, error, onRetry, onKeywordClick }) {
  const [activeKeyword, setActiveKeyword] = useState(null)

  if (loading) {
    return (
      <div className="card">
        <h3>Keywords</h3>
        <SkeletonBlock label="Extracting keywords…" />
      </div>
    )
  }
  if (error) {
    return (
      <div className="card">
        <h3>Keywords</h3>
        <ErrorState message={error} actionLabel={onRetry ? 'Retry' : undefined} onAction={onRetry} />
      </div>
    )
  }
  if (!keywords || keywords.length === 0) {
    return (
      <div className="card">
        <EmptyState title="No keywords available" description="Important terms extracted from the lecture will appear here once processing completes." />
      </div>
    )
  }

  function handleClick(k) {
    setActiveKeyword(k)
    if (onKeywordClick) onKeywordClick(k)
  }

  return (
    <div className="card">
      <h3>Important Keywords</h3>
      <p className="hint">Click a keyword to search for it in the transcript.</p>
      <div className="keyword-chips">
        {keywords.map((k, i) => (
          <button
            key={i}
            className={`keyword-chip ${activeKeyword === k ? 'keyword-chip-active' : ''}`}
            onClick={() => handleClick(k)}
          >
            {k}
          </button>
        ))}
      </div>
    </div>
  )
}
