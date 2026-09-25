import { useState, useEffect, useCallback } from 'react'
import { useApp } from '../context/AppContext'
import { listLectures, getStats } from '../services/api'
import EmptyState from '../components/EmptyState'
import { SkeletonBlock } from '../components/Skeleton'
import { formatDuration, formatDate } from '../services/format'

const FILE_TYPE_LABEL = {
  video: 'Video',
  audio: 'Audio',
}

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
      const [listRes, statsRes] = await Promise.all([
        listLectures(),
        getStats(),
      ])

      setLectures(listRes.lectures)
      setStats(statsRes)
    } catch (e) {
      setError(e.message || 'Failed to load dashboard data.')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    load()
  }, [load, refreshToken])

  const recentLectures = (lectures || []).slice(0, 5)

  return (
    <div className="page-dashboard">

      {/* Hero */}
      <section className="dashboard-intro">

        <div className="dashboard-intro-copy">
          <p className="dashboard-eyebrow">LECTURE LIBRARY</p>

          <h1>Good afternoon, Mohsin.</h1>

          <p className="dashboard-subtitle">
            Everything you've learned, in one place.
          </p>
        </div>

        <button
          className="dashboard-add-button"
          onClick={() => navigate('upload')}
        >
          <span>+</span>
          Add lecture
        </button>

      </section>

      {/* Small overview */}
      {!loading && !error && stats && (
        <div className="dashboard-overview">

          <span>
            {stats.total_lectures}{' '}
            {stats.total_lectures === 1 ? 'lecture' : 'lectures'}
          </span>

          <span className="dashboard-overview-dot">·</span>

          <span>
            {formatDuration(stats.total_duration_seconds)} total
          </span>

        </div>
      )}

      {/* Error */}
      {!loading && error && (
        <div className="dashboard-error">
          <p>{error}</p>
        </div>
      )}

      {/* Recent lectures */}
      <section className="dashboard-library">

        <div className="dashboard-section-header">
          <div>
            <p className="dashboard-section-label">RECENT</p>
            <h2>Your lectures</h2>
          </div>

          {recentLectures.length > 0 && (
            <button
              className="dashboard-view-all"
              onClick={() => navigate('library')}
            >
              View all
              <span>→</span>
            </button>
          )}
        </div>

        {loading && (
          <div className="dashboard-loading">
            <SkeletonBlock />
            <SkeletonBlock />
          </div>
        )}

        {!loading && recentLectures.length === 0 && !error && (
          <div className="dashboard-empty">
            <EmptyState
              title="No lectures yet"
              description="Add your first lecture to start building your library."
              actionLabel="Add lecture"
              onAction={() => navigate('upload')}
            />
          </div>
        )}

        {!loading && recentLectures.length > 0 && (
          <div className="dashboard-lecture-list">

            {recentLectures.map((lecture) => (
              <button
                key={lecture.lecture_id}
                className="dashboard-lecture-row"
                onClick={() =>
                  navigate('lecture', lecture.lecture_id)
                }
              >

                <div className="dashboard-lecture-main">

                  <div className="dashboard-lecture-index">
                    {String(
                      recentLectures.indexOf(lecture) + 1
                    ).padStart(2, '0')}
                  </div>

                  <div className="dashboard-lecture-info">

                    <span className="dashboard-lecture-title">
                      {lecture.original_filename}
                    </span>

                    <span className="dashboard-lecture-meta">
                      {FILE_TYPE_LABEL[lecture.file_type] ||
                        lecture.file_type}

                      <span>·</span>

                      {formatDuration(lecture.duration_seconds)}

                      <span>·</span>

                      {lecture.question_count || 0}{' '}
                      {(lecture.question_count || 0) === 1
                        ? 'question'
                        : 'questions'}
                    </span>
                

                   

                  </div>

                </div>

                <div className="dashboard-lecture-end">

                  <span className="dashboard-lecture-date">
                    {formatDate(lecture.upload_time)}
                  </span>

                  <span className="dashboard-lecture-arrow">
                    →
                  </span>

                </div>

              </button>
            ))}

          </div>
        )}

      </section>

    </div>
  )
}