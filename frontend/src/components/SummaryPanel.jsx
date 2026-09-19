import EmptyState from './EmptyState'
import ErrorState from './ErrorState'
import { SkeletonBlock } from './Skeleton'

export default function SummaryPanel({ summary, loading, error, onRetry }) {
  if (loading) {
    return (
      <div className="card">
        <h3>Summary</h3>
        <SkeletonBlock label="Generating summary…" />
      </div>
    )
  }
  if (error) {
    return (
      <div className="card">
        <h3>Summary</h3>
        <ErrorState message={error} actionLabel={onRetry ? 'Retry' : undefined} onAction={onRetry} />
      </div>
    )
  }
  if (!summary) {
    return (
      <div className="card">
        <EmptyState title="No summary available" description="A structured summary will appear here once processing completes." />
      </div>
    )
  }

  return (
    <div className="summary-grid">
      <div className="card summary-overview-card">
        <h4 className="summary-section-label">Overview</h4>
        <p>{summary.overview || 'No overview was generated for this lecture.'}</p>
      </div>

      {summary.main_concepts?.length > 0 && (
        <div className="card">
          <h4 className="summary-section-label">Main Concepts</h4>
          <ul className="summary-list">
            {summary.main_concepts.map((c, i) => <li key={i}>{c}</li>)}
          </ul>
        </div>
      )}

      {summary.important_points?.length > 0 && (
        <div className="card">
          <h4 className="summary-section-label">Important Points</h4>
          <ul className="summary-list">
            {summary.important_points.map((p, i) => <li key={i}>{p}</li>)}
          </ul>
        </div>
      )}

      {summary.key_takeaways?.length > 0 && (
        <div className="card">
          <h4 className="summary-section-label">Key Takeaways</h4>
          <ul className="summary-list summary-list-takeaways">
            {summary.key_takeaways.map((k, i) => <li key={i}>{k}</li>)}
          </ul>
        </div>
      )}
    </div>
  )
}
