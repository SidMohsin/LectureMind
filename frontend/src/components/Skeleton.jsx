export function SkeletonLine({ width = '100%' }) {
  return <div className="skeleton-line" style={{ width }} />
}

export function SkeletonBlock({ label }) {
  return (
    <div className="skeleton-block" role="status" aria-live="polite">
      <SkeletonLine width="70%" />
      <SkeletonLine width="95%" />
      <SkeletonLine width="85%" />
      {label && <span className="skeleton-label">{label}</span>}
    </div>
  )
}
