export default function StatusBadge({ status }) {
  let cls = 'status-badge '
  let label = status

  if (status === 'completed') { cls += 'status-completed'; label = 'Ready' }
  else if (status === 'failed') { cls += 'status-failed'; label = 'Failed' }
  else if (status === 'uploaded') { cls += 'status-uploaded'; label = 'Uploaded' }
  else { cls += 'status-processing'; label = 'Processing' }

  return <span className={cls}>{label}</span>
}
