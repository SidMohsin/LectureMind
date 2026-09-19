export default function ErrorState({ title = 'Something went wrong', message, actionLabel, onAction }) {
  return (
    <div className="error-state">
      <div className="error-state-icon" aria-hidden="true">!</div>
      <div className="error-state-body">
        <h4>{title}</h4>
        {message && <p>{message}</p>}
        {actionLabel && onAction && (
          <button className="btn-secondary btn-inline" onClick={onAction}>{actionLabel}</button>
        )}
      </div>
    </div>
  )
}
