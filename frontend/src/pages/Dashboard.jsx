import { useState, useEffect, useCallback } from 'react'
import { useApp } from '../context/AppContext'
import { useAuth } from '../context/AuthContext'
import { listLectures, getStats } from '../services/api'
import EmptyState from '../components/EmptyState'
import { SkeletonBlock } from '../components/Skeleton'
import { formatDuration, formatDate } from '../services/format'

const FILE_TYPE_LABEL = { video: 'Video', audio: 'Audio' }

function getGreeting() {
  const h = new Date().getHours()
  if (h >= 5 && h < 12) return 'Good morning'
  if (h >= 12 && h < 17) return 'Good afternoon'
  return 'Good evening'
}

export default function Dashboard() {
  const { navigate, refreshToken } = useApp()
  const { user } = useAuth()

  const [lectures, setLectures] = useState(null)
  const [stats, setStats] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [greeting, setGreeting] = useState(getGreeting)

  // Update greeting every minute
  useEffect(() => {
    const interval = setInterval(() => setGreeting(getGreeting()), 60000)
    return () => clearInterval(interval)
  }, [])

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const [listRes, statsRes] = await Promise.all([listLectures(), getStats()])
      setLectures(listRes.lectures)
      setStats(statsRes)
    } catch (e) {
      setError(e.message || 'Failed to load data.')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { load() }, [load, refreshToken])

  const firstName = user?.name?.split(' ')[0] || 'there'
  const recentLectures = (lectures || []).slice(0, 6)
  const featuredLecture = recentLectures[0] || null

  return (
    <div className="page-dashboard">

      {/* Hero greeting */}
      <div className="dashboard-hero">
        <div className="dashboard-hero-copy">
          <p className="dashboard-eyebrow">Your library</p>
          <h1>{greeting}, {firstName}.</h1>
          <p className="dashboard-hero-sub">
            Turn every recording into a study-ready resource.
          </p>
        </div>
        <button className="dashboard-add-btn" onClick={() => navigate('upload')}>
          <span className="dashboard-add-btn-plus">+</span>
          Add lecture
        </button>
      </div>

      {/* Stats summary — subtle, not cards */}
      {!loading && !error && stats && (
        <div className="dashboard-overview">
          <span>{stats.total_lectures} {stats.total_lectures === 1 ? 'lecture' : 'lectures'}</span>
          <span className="dashboard-overview-dot">·</span>
          <span>{formatDuration(stats.total_duration_seconds)} total</span>
        </div>
      )}

      {/* Continue learning / Featured */}
      {!loading && featuredLecture && (
        <div className="dashboard-featured">
          <div className="dashboard-section-hdr">
            <span className="dashboard-section-label">Pick up where you left off</span>
          </div>
          <div
            className="featured-card"
            role="button"
            tabIndex={0}
            onClick={() => navigate('lecture', featuredLecture.lecture_id)}
            onKeyDown={(e) => { if (e.key === 'Enter') navigate('lecture', featuredLecture.lecture_id) }}
          >
            <div>
              <p className="featured-meta">
                {FILE_TYPE_LABEL[featuredLecture.file_type] || featuredLecture.file_type}
                {' · '}
                {formatDuration(featuredLecture.duration_seconds)}
              </p>
              <p className="featured-title">{featuredLecture.original_filename}</p>
              <div className="featured-sub">
                <span>Opened {formatDate(featuredLecture.upload_time)}</span>
                {featuredLecture.question_count > 0 && (
                  <>
                    <span className="featured-dot">·</span>
                    <span>{featuredLecture.question_count} {featuredLecture.question_count === 1 ? 'question asked' : 'questions asked'}</span>
                  </>
                )}
              </div>
            </div>
            <button
              className="featured-continue"
              tabIndex={-1}
              onClick={(e) => { e.stopPropagation(); navigate('lecture', featuredLecture.lecture_id) }}
            >
              Open →
            </button>
          </div>
        </div>
      )}

      {/* Recent lectures */}
      <div className="dashboard-library">
        <div className="dashboard-section-hdr">
            <span className="dashboard-section-label">Recent lectures</span>
          {recentLectures.length > 0 && (
            <button className="dashboard-view-all" onClick={() => navigate('library')}>
              View all <span>→</span>
            </button>
          )}
        </div>

        {loading && (
          <div className="dashboard-loading">
            <SkeletonBlock />
            <SkeletonBlock />
          </div>
        )}

        {!loading && error && (
          <div className="dashboard-error">
            <p className="hint">{error}</p>
          </div>
        )}

        {!loading && !error && recentLectures.length === 0 && (
          <div className="dashboard-empty">
            <EmptyState
              title="No lectures yet"
              description="Upload your first lecture to start building your personal knowledge library."
              actionLabel="Add lecture"
              onAction={() => navigate('upload')}
            />
          </div>
        )}

        {!loading && !error && recentLectures.length > 0 && (
          <div className="dashboard-lecture-list">
            {recentLectures.map((lecture, idx) => (
              <button
                key={lecture.lecture_id}
                className="dashboard-lecture-row"
                onClick={() => navigate('lecture', lecture.lecture_id)}
              >
                <div className="dashboard-lecture-index">
                  {String(idx + 1).padStart(2, '0')}
                </div>
                <div className="dashboard-lecture-info">
                  <span className="dashboard-lecture-title">
                    {lecture.original_filename}
                  </span>
                  <span className="dashboard-lecture-meta">
                    {FILE_TYPE_LABEL[lecture.file_type] || lecture.file_type}
                    <span>·</span>
                    {formatDuration(lecture.duration_seconds)}
                    <span>·</span>
                    {(lecture.question_count || 0)} {(lecture.question_count || 0) === 1 ? 'question' : 'questions'}
                  </span>
                </div>
                <div className="dashboard-lecture-end">
                  <span className="dashboard-lecture-date">{formatDate(lecture.upload_time)}</span>
                  <span className="dashboard-lecture-arrow">→</span>
                </div>
              </button>
            ))}
          </div>
        )}
      </div>

    </div>
  )
}
