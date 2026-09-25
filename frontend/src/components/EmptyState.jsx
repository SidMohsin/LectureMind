export default function EmptyState({ title, description, actionLabel, onAction }) {
  return (
    <div className="empty-state">
      <div className="empty-icon">○</div>
      <p className="empty-title">{title}</p>
      {description && <p className="empty-desc">{description}</p>}
      {actionLabel && onAction && (
        <button className="btn-primary btn-small" style={{ marginTop: 12 }} onClick={onAction}>
          {actionLabel}
        </button>
      )}
    </div>
  )
}
