import { statusBadgeLabel } from '../services/format'

export default function StatusBadge({ status }) {
  const bucket = status === 'completed' ? 'completed'
    : status === 'failed' ? 'failed'
    : status === 'uploaded' ? 'uploaded'
    : 'processing'
  return <span className={`status-pill status-pill-${bucket}`}>{statusBadgeLabel(status)}</span>
}
