export function SkeletonBlock({ label }) {
  return (
    <div className="skeleton-block">
      {label && <p className="skeleton-label">{label}</p>}
      <div className="skeleton-line skeleton-line-long" />
      <div className="skeleton-line skeleton-line-short" />
      <div className="skeleton-line skeleton-line-long" style={{ width: '55%' }} />
    </div>
  )
}
