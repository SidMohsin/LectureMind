import { useState, useEffect, useCallback } from 'react'
import { useApp } from '../context/AppContext'
import { listLectures, getStats } from '../services/api'
import StatCard from '../components/StatCard'
import LectureRow from '../components/LectureRow'
import EmptyState from '../components/EmptyState'
import { SkeletonBlock } from '../components/Skeleton'
import { formatDuration } from '../services/format'

export default function Dashboard() {
  const { navigate, refreshToken } = useApp()

  const [lectures, setLectures] = useState(null)
  const [stats, setStats] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const [listRes, statsRes] = await Promise.all([listLectures(), getStats()])
      setLectures(listRes.lectures)
      setStats(statsRes)
    } catch (e) {
      setError(e.message || 'Failed to load dashboard data.')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { load() }, [load, refreshToken])

  const recentLectures = (lectures || []).slice(0, 5)

  return (
    <div className="page-dashboard">
      <section className="welcome-card">
        <div>
          <h1>Welcome to LectureMind</h1>
          <p>Turn your lectures into searchable knowledge.</p>
        </div>
        <div className="welcome-actions">
          <button className="btn-primary btn-inline" onClick={() => navigate('upload')}>Upload New Lecture</button>
          <button className="btn-secondary btn-inline" onClick={() => navigate('library')}>View My Lectures</button>
        </div>
      </section>

      {loading && (
        <div className="stats-grid">
          <SkeletonBlock /><SkeletonBlock /><SkeletonBlock /><SkeletonBlock />
        </div>
      )}

      {!loading && error && (
        <div className="card"><p className="error-banner">{error}</p></div>
      )}

      {!loading && !error && stats && (
        <div className="stats-grid">
          <StatCard label="Total Lectures" value={stats.total_lectures} />
          <StatCard label="Processed Lectures" value={stats.completed_lectures} />
          <StatCard label="Total Duration" value={formatDuration(stats.total_duration_seconds)} />
          <StatCard label="Questions Asked" value={stats.total_questions_asked} />
        </div>
      )}

      <section className="card">
        <div className="panel-header-row">
          <h3>Recent Lectures</h3>
          {recentLectures.length > 0 && (
            <button className="btn-secondary btn-small" onClick={() => navigate('library')}>View all</button>
          )}
        </div>

        {loading && <SkeletonBlock label="Loading lectures…" />}

        {!loading && recentLectures.length === 0 && !error && (
          <EmptyState
            title="No lectures yet"
            description="Upload your first lecture and LectureMind will turn it into searchable knowledge."
            actionLabel="Upload Lecture"
            onAction={() => navigate('upload')}
          />
        )}

        {!loading && recentLectures.length > 0 && (
          <div className="lecture-row-list">
            {recentLectures.map((l) => (
              <LectureRow key={l.lecture_id} lecture={l} onOpen={(id) => navigate('lecture', id)} />
            ))}
          </div>
        )}
      </section>
    </div>
  )
}
