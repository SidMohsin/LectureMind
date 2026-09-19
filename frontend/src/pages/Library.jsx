import { useState, useEffect, useCallback, useMemo } from 'react'
import { useApp } from '../context/AppContext'
import { listLectures, deleteLecture } from '../services/api'
import LectureRow from '../components/LectureRow'
import EmptyState from '../components/EmptyState'
import ConfirmDialog from '../components/ConfirmDialog'
import { SkeletonBlock } from '../components/Skeleton'
import { statusBucket } from '../services/format'

const FILTERS = [
  { key: 'all', label: 'All' },
  { key: 'completed', label: 'Completed' },
  { key: 'processing', label: 'Processing' },
  { key: 'uploaded', label: 'Uploaded' },
  { key: 'failed', label: 'Failed' },
]

const SORTS = [
  { key: 'newest', label: 'Newest first' },
  { key: 'oldest', label: 'Oldest first' },
  { key: 'name', label: 'Name (A–Z)' },
]

export default function Library() {
  const { navigate, refreshToken, triggerRefresh } = useApp()

  const [lectures, setLectures] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  const [query, setQuery] = useState('')
  const [filter, setFilter] = useState('all')
  const [sort, setSort] = useState('newest')

  const [pendingDelete, setPendingDelete] = useState(null)
  const [deleting, setDeleting] = useState(false)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const res = await listLectures()
      setLectures(res.lectures)
    } catch (e) {
      setError(e.message || 'Failed to load lectures.')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { load() }, [load, refreshToken])

  useEffect(() => {
    function handleExternalSearch(e) {
      setQuery(e.detail)
    }
    window.addEventListener('lecturemind:search', handleExternalSearch)
    return () => window.removeEventListener('lecturemind:search', handleExternalSearch)
  }, [])

  const filtered = useMemo(() => {
    if (!lectures) return []
    let items = lectures
    if (query.trim()) {
      const q = query.trim().toLowerCase()
      items = items.filter((l) => l.original_filename.toLowerCase().includes(q))
    }
    if (filter !== 'all') {
      items = items.filter((l) => statusBucket(l.status) === filter)
    }
    items = [...items]
    if (sort === 'newest') items.sort((a, b) => new Date(b.upload_time) - new Date(a.upload_time))
    else if (sort === 'oldest') items.sort((a, b) => new Date(a.upload_time) - new Date(b.upload_time))
    else if (sort === 'name') items.sort((a, b) => a.original_filename.localeCompare(b.original_filename))
    return items
  }, [lectures, query, filter, sort])

  async function confirmDelete() {
    if (!pendingDelete) return
    setDeleting(true)
    try {
      await deleteLecture(pendingDelete.lecture_id)
      setPendingDelete(null)
      triggerRefresh()
      await load()
    } catch (e) {
      setError(e.message || 'Failed to delete lecture.')
      setPendingDelete(null)
    } finally {
      setDeleting(false)
    }
  }

  return (
    <div className="page-library">
      <div className="page-header-row">
        <h1>My Lectures</h1>
        <button className="btn-primary btn-inline" onClick={() => navigate('upload')}>Upload Lecture</button>
      </div>

      <div className="library-toolbar">
        <input
          type="search"
          className="panel-search-input library-search"
          placeholder="Search lectures by filename…"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
        />
        <div className="library-filters">
          {FILTERS.map((f) => (
            <button
              key={f.key}
              className={`filter-chip ${filter === f.key ? 'filter-chip-active' : ''}`}
              onClick={() => setFilter(f.key)}
            >
              {f.label}
            </button>
          ))}
        </div>
        <select className="library-sort" value={sort} onChange={(e) => setSort(e.target.value)} aria-label="Sort lectures">
          {SORTS.map((s) => <option key={s.key} value={s.key}>{s.label}</option>)}
        </select>
      </div>

      <div className="card">
        {loading && <SkeletonBlock label="Loading lectures…" />}

        {!loading && error && <p className="error-banner">{error}</p>}

        {!loading && !error && filtered.length === 0 && (lectures || []).length === 0 && (
          <EmptyState
            title="No lectures yet"
            description="Upload your first lecture and LectureMind will turn it into searchable knowledge."
            actionLabel="Upload Lecture"
            onAction={() => navigate('upload')}
          />
        )}

        {!loading && !error && filtered.length === 0 && (lectures || []).length > 0 && (
          <p className="hint">No lectures match your search/filter.</p>
        )}

        {!loading && !error && filtered.length > 0 && (
          <div className="lecture-row-list">
            {filtered.map((l) => (
              <LectureRow
                key={l.lecture_id}
                lecture={l}
                onOpen={(id) => navigate('lecture', id)}
                onDelete={(lecture) => setPendingDelete(lecture)}
              />
            ))}
          </div>
        )}
      </div>

      <ConfirmDialog
        open={!!pendingDelete}
        title="Delete this lecture?"
        message={pendingDelete ? `"${pendingDelete.original_filename}" and all of its transcript, summary, keywords, and indexed data will be permanently deleted. This cannot be undone.` : ''}
        confirmLabel={deleting ? 'Deleting…' : 'Delete'}
        danger
        onConfirm={confirmDelete}
        onCancel={() => setPendingDelete(null)}
      />
    </div>
  )
}
