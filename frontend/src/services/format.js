// Formatting helpers shared across components.

export function formatTimestamp(seconds) {
  if (seconds === null || seconds === undefined || isNaN(seconds)) return '--:--'
  const total = Math.round(seconds)
  const mm = Math.floor(total / 60).toString().padStart(2, '0')
  const ss = (total % 60).toString().padStart(2, '0')
  return `${mm}:${ss}`
}

export function formatTimeRange(start, end) {
  return `[${formatTimestamp(start)} - ${formatTimestamp(end)}]`
}

/** Formats seconds as "42 min" or "1h 05m" for display in lecture cards. */
export function formatDuration(seconds) {
  if (seconds === null || seconds === undefined || isNaN(seconds) || seconds <= 0) return '—'
  const totalMinutes = Math.round(seconds / 60)
  if (totalMinutes < 60) return `${totalMinutes} min`
  const h = Math.floor(totalMinutes / 60)
  const m = totalMinutes % 60
  return `${h}h ${m.toString().padStart(2, '0')}m`
}

/** Formats an ISO date string as e.g. "Aug 20, 2026". */
export function formatDate(isoString) {
  if (!isoString) return '—'
  try {
    const d = new Date(isoString)
    return d.toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' })
  } catch (e) {
    return isoString
  }
}

/** Formats an ISO date string as e.g. "Aug 20, 2026, 10:15 AM". */
export function formatDateTime(isoString) {
  if (!isoString) return '—'
  try {
    const d = new Date(isoString)
    return d.toLocaleString(undefined, {
      year: 'numeric', month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit',
    })
  } catch (e) {
    return isoString
  }
}

export const STATUS_LABELS = {
  uploaded: 'Uploaded',
  queued: 'Queued',
  extracting_audio: 'Extracting audio',
  transcribing: 'Transcribing with Whisper',
  cleaning: 'Cleaning transcript',
  chunking: 'Creating chunks',
  embedding: 'Generating embeddings',
  indexing: 'Indexing in ChromaDB',
  summarizing: 'Generating summary',
  extracting_keywords: 'Extracting keywords',
  completed: 'Completed',
  failed: 'Failed',
}

export const STATUS_ORDER = [
  'uploaded', 'queued', 'extracting_audio', 'transcribing', 'cleaning',
  'chunking', 'embedding', 'indexing', 'summarizing', 'extracting_keywords', 'completed',
]

/** Short badge label for a status, used in compact lecture cards/tables. */
export function statusBadgeLabel(status) {
  if (status === 'completed') return 'Completed'
  if (status === 'failed') return 'Failed'
  if (status === 'uploaded') return 'Uploaded'
  return 'Processing'
}

/** Coarse status bucket, used for filtering the lecture library. */
export function statusBucket(status) {
  if (status === 'completed') return 'completed'
  if (status === 'failed') return 'failed'
  if (status === 'uploaded') return 'uploaded'
  return 'processing'
}
