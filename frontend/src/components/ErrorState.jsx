export default function ErrorState({ message, actionLabel, onAction }) {
  return (
    <div className="error-state">
      <p>{message || 'Something went wrong.'}</p>
      {actionLabel && onAction && (
        <button className="btn-secondary btn-small" style={{ marginTop: 12 }} onClick={onAction}>
          {actionLabel}
        </button>
      )}
    </div>
  )
}
