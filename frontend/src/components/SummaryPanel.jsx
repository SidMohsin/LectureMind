import EmptyState from './EmptyState'
import ErrorState from './ErrorState'
import { SkeletonBlock } from './Skeleton'

export default function SummaryPanel({ summary, loading, error, onRetry }) {
  if (loading) return (
    <div className="summary-area">
      <SkeletonBlock label="Generating summary…" />
    </div>
  )

  if (error) return (
    <div className="summary-area">
      <ErrorState message={error} actionLabel={onRetry ? 'Retry' : undefined} onAction={onRetry} />
    </div>
  )

  if (!summary) return (
    <div className="summary-area">
      <EmptyState
        title="No summary available"
        description="A structured summary will appear here once processing completes."
      />
    </div>
  )

  return (
    <div className="summary-area">
      <h3>Summary</h3>

      {summary.overview && (
        <p className="summary-overview">{summary.overview}</p>
      )}

      {summary.main_concepts?.length > 0 && (
        <div className="summary-section">
          <p className="summary-section-title">Main Concepts</p>
          <ul className="summary-items">
            {summary.main_concepts.map((c, i) => (
              <li key={i}>
                <span className="summary-item-num">{String(i + 1).padStart(2, '0')}</span>
                <span>{c}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {summary.important_points?.length > 0 && (
        <div className="summary-section">
          <p className="summary-section-title">Key Ideas</p>
          <ul className="summary-items">
            {summary.important_points.map((p, i) => (
              <li key={i}>
                <span className="summary-item-num">{String(i + 1).padStart(2, '0')}</span>
                <span>{p}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {summary.key_takeaways?.length > 0 && (
        <div className="summary-section">
          <p className="summary-section-title">Key Takeaways</p>
          <ul className="summary-items">
            {summary.key_takeaways.map((k, i) => (
              <li key={i}>
                <span className="summary-item-num">{String(i + 1).padStart(2, '0')}</span>
                <span>{k}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  )
}
