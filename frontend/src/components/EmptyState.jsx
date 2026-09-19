export default function EmptyState({ icon = '—', title, description, actionLabel, onAction }) {
  return (
    <div className="empty-state">
      <div className="empty-state-icon" aria-hidden="true">{icon}</div>
      <h3>{title}</h3>
      {description && <p>{description}</p>}
      {actionLabel && onAction && (
        <button className="btn-primary btn-inline" onClick={onAction}>{actionLabel}</button>
      )}
    </div>
  )
}
