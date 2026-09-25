import { STATUS_LABELS, STATUS_ORDER } from '../services/format'

export default function ProcessingStages({ status, statusMessage, errorMessage, onRetry }) {
  if (!status) return null

  if (status === 'failed') {
    return (
      <div className="processing-area processing-failed">
        <h3>Processing failed</h3>
        <p>{errorMessage || 'An error occurred while processing this lecture.'}</p>
        {onRetry && (
          <button className="btn-secondary btn-inline" onClick={onRetry}>
            Retry processing
          </button>
        )}
      </div>
    )
  }

  const currentIndex = STATUS_ORDER.indexOf(status)
  const total = STATUS_ORDER.length
  const percent = currentIndex >= 0 ? Math.round(((currentIndex + 1) / total) * 100) : 0

  return (
    <div className="processing-area">
      <div className="processing-hdr">
        <h3>Processing lecture</h3>
        <span className="processing-percent">{percent}%</span>
      </div>

      <div className="processing-bar-outer">
        <div className="processing-bar-inner" style={{ width: `${percent}%` }} />
      </div>

      <p className="processing-message">{statusMessage || STATUS_LABELS[status] || status}</p>

      <ol className="processing-steps">
        {STATUS_ORDER.filter(s => s !== 'completed').map((step, idx) => {
          let cls = 'processing-step'
          if (idx < currentIndex) cls += ' step-done'
          else if (idx === currentIndex) cls += ' step-active'
          return (
            <li key={step} className={cls}>
              <span className="step-marker" aria-hidden="true">
                {idx < currentIndex ? '✓' : idx === currentIndex ? '·' : ''}
              </span>
              <span className="step-label">{STATUS_LABELS[step]}</span>
            </li>
          )
        })}
      </ol>
    </div>
  )
}
