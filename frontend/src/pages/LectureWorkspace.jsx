import { useState, useEffect, useCallback, useRef } from 'react'
import { useApp } from '../context/AppContext'
import {
  getLecture, getStatus, getTranscript, getSummary, getKeywords,
  startProcessing, deleteLecture,
} from '../services/api'
import ProcessingStages from '../components/ProcessingStages'
import MediaPlayer from '../components/MediaPlayer'
import TranscriptPanel from '../components/TranscriptPanel'
import SummaryPanel from '../components/SummaryPanel'
import KeywordsPanel from '../components/KeywordsPanel'
import ChatPanel from '../components/ChatPanel'
import StatusBadge from '../components/StatusBadge'
import ConfirmDialog from '../components/ConfirmDialog'
import { formatDuration, formatDate } from '../services/format'

const TABS = ['Transcript', 'Summary', 'Keywords', 'Ask']

export default function LectureWorkspace({ lectureId }) {
  const { navigate, triggerRefresh } = useApp()
  const playerRef = useRef(null)
  const pollRef = useRef(null)

  const [lecture, setLecture] = useState(null)
  const [loadingLecture, setLoadingLecture] = useState(true)
  const [loadError, setLoadError] = useState(null)

  const [activeTab, setActiveTab] = useState('Transcript')
  const [currentTime, setCurrentTime] = useState(0)
  const [transcriptSearch, setTranscriptSearch] = useState('')

  const [transcript, setTranscript] = useState(null)
  const [transcriptLoading, setTranscriptLoading] = useState(false)
  const [transcriptError, setTranscriptError] = useState(null)

  const [summary, setSummary] = useState(null)
  const [summaryLoading, setSummaryLoading] = useState(false)
  const [summaryError, setSummaryError] = useState(null)

  const [keywords, setKeywords] = useState(null)
  const [keywordsLoading, setKeywordsLoading] = useState(false)
  const [keywordsError, setKeywordsError] = useState(null)

  const [confirmDelete, setConfirmDelete] = useState(false)
  const [deleting, setDeleting] = useState(false)

  const loadLecture = useCallback(async () => {
    setLoadingLecture(true)
    setLoadError(null)
    try {
      const l = await getLecture(lectureId)
      setLecture(l)
      return l
    } catch (e) {
      setLoadError(e.message || 'Failed to load this lecture.')
      return null
    } finally {
      setLoadingLecture(false)
    }
  }, [lectureId])

  const fetchResults = useCallback(async () => {
    setTranscriptLoading(true); setSummaryLoading(true); setKeywordsLoading(true)
    setTranscriptError(null); setSummaryError(null); setKeywordsError(null)
    try { setTranscript(await getTranscript(lectureId)) }
    catch (e) { setTranscriptError(e.message) }
    finally { setTranscriptLoading(false) }
    try { setSummary(await getSummary(lectureId)) }
    catch (e) { setSummaryError(e.message) }
    finally { setSummaryLoading(false) }
    try { const k = await getKeywords(lectureId); setKeywords(k.keywords) }
    catch (e) { setKeywordsError(e.message) }
    finally { setKeywordsLoading(false) }
  }, [lectureId])

  const pollStatus = useCallback(() => {
    if (pollRef.current) clearInterval(pollRef.current)
    pollRef.current = setInterval(async () => {
      try {
        const s = await getStatus(lectureId)
        setLecture((prev) => prev ? { ...prev, status: s.status, status_message: s.status_message, error_message: s.error_message } : prev)
        if (s.status === 'completed' || s.status === 'failed') {
          clearInterval(pollRef.current)
          triggerRefresh()
          if (s.status === 'completed') {
            await loadLecture()
            fetchResults()
          }
        }
      } catch (e) {
        clearInterval(pollRef.current)
      }
    }, 2500)
  }, [lectureId, fetchResults, loadLecture, triggerRefresh])

  useEffect(() => {
    setTranscript(null); setSummary(null); setKeywords(null)
    setActiveTab('Transcript'); setTranscriptSearch(''); setCurrentTime(0)
    loadLecture().then((l) => {
      if (!l) return
      const processingStatuses = new Set([
        'uploaded', 'queued', 'extracting_audio', 'transcribing', 'cleaning',
        'chunking', 'embedding', 'indexing', 'summarizing', 'extracting_keywords',
      ])
      if (l.status === 'completed') fetchResults()
      else if (processingStatuses.has(l.status)) pollStatus()
    })
    return () => { if (pollRef.current) clearInterval(pollRef.current) }
  }, [lectureId]) // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    const storageKey = `lecturemind:seek:${lectureId}`
    const target = sessionStorage.getItem(storageKey)
    if (!target || lecture?.status !== 'completed') return
    const seconds = Number(target)
    sessionStorage.removeItem(storageKey)
    if (!Number.isFinite(seconds)) return
    setActiveTab('Transcript')
    setCurrentTime(seconds)
    const timer = setTimeout(() => playerRef.current?.seek(seconds), 100)
    return () => clearTimeout(timer)
  }, [lecture, lectureId])

  function handleSeek(seconds) {
    if (playerRef.current) playerRef.current.seek(seconds)
    setCurrentTime(seconds)
  }

  function handleKeywordClick(keyword) {
    setTranscriptSearch(keyword)
    setActiveTab('Transcript')
  }

  async function handleRetryProcessing() {
    try {
      await startProcessing(lectureId)
      setLecture((prev) => prev ? { ...prev, status: 'queued', status_message: 'Processing queued', error_message: null } : prev)
      pollStatus()
    } catch (e) {
      setLoadError(e.message || 'Failed to restart processing.')
    }
  }

  async function handleDelete() {
    setDeleting(true)
    try {
      await deleteLecture(lectureId)
      triggerRefresh()
      navigate('library')
    } catch (e) {
      setLoadError(e.message || 'Failed to delete this lecture.')
      setConfirmDelete(false)
    } finally {
      setDeleting(false)
    }
  }

  function handleDownloadTranscript(format) {
    if (!transcript) return
    let content, mime, filename
    const baseName = (lecture?.original_filename || 'transcript').replace(/\.[^.]+$/, '')
    if (format === 'json') {
      content = JSON.stringify(transcript, null, 2)
      mime = 'application/json'
      filename = `${baseName}_transcript.json`
    } else {
      content = transcript.segments
        .map((s) => `[${Math.floor(s.start / 60)}:${String(Math.floor(s.start % 60)).padStart(2, '0')}] ${s.text}`)
        .join('\n')
      mime = 'text/plain'
      filename = `${baseName}_transcript.txt`
    }
    const blob = new Blob([content], { type: mime })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url; a.download = filename
    document.body.appendChild(a); a.click()
    document.body.removeChild(a); URL.revokeObjectURL(url)
  }

  if (loadingLecture && !lecture) {
    return (
      <div className="page-workspace">
        <p className="hint" style={{ paddingTop: 40, textAlign: 'center' }}>Loading lecture…</p>
      </div>
    )
  }
  if (loadError && !lecture) {
    return (
      <div className="page-workspace">
        <p className="error-banner">{loadError}</p>
      </div>
    )
  }
  if (!lecture) return null

  const processingStatuses = new Set([
    'uploaded', 'queued', 'extracting_audio', 'transcribing', 'cleaning',
    'chunking', 'embedding', 'indexing', 'summarizing', 'extracting_keywords',
  ])
  const isProcessing = processingStatuses.has(lecture.status)
  const isCompleted = lecture.status === 'completed'
  const isFailed = lecture.status === 'failed'

  return (
    <div className="page-workspace">

      {/* Header */}
      <div className="workspace-header">
        <button className="link-back" onClick={() => navigate('library')}>
          ← Library
        </button>

        <div className="workspace-title-row">
          <div style={{ flex: 1, minWidth: 0 }}>
            <h1 className="workspace-title">{lecture.original_filename}</h1>
            <div className="workspace-meta">
              <StatusBadge status={lecture.status} />
              <span className="workspace-meta-dot">·</span>
              <span className="workspace-meta-item">
                {lecture.file_type === 'video' ? 'Video' : 'Audio'}
              </span>
              <span className="workspace-meta-dot">·</span>
              <span className="workspace-meta-item">{formatDuration(lecture.duration_seconds)}</span>
              <span className="workspace-meta-dot">·</span>
              <span className="workspace-meta-item">{formatDate(lecture.upload_time)}</span>
            </div>
          </div>

          <div className="workspace-actions">
            {isCompleted && transcript && (
              <>
                <button className="btn-secondary btn-small" onClick={() => handleDownloadTranscript('txt')}>
                  .txt
                </button>
                <button className="btn-secondary btn-small" onClick={() => handleDownloadTranscript('json')}>
                  .json
                </button>
              </>
            )}
            <button className="btn-danger btn-small" onClick={() => setConfirmDelete(true)}>
              Delete
            </button>
          </div>
        </div>
      </div>

      {loadError && <div className="error-banner" style={{ marginBottom: 20 }}>{loadError}</div>}

      {/* Processing state */}
      {(isProcessing || isFailed) && (
        <ProcessingStages
          status={lecture.status}
          statusMessage={lecture.status_message}
          errorMessage={lecture.error_message}
          onRetry={isFailed ? handleRetryProcessing : undefined}
        />
      )}

      {/* Completed workspace */}
      {isCompleted && (
        <>
          {lecture.has_media && (
            <MediaPlayer
              ref={playerRef}
              lectureId={lectureId}
              fileType={lecture.file_type}
              onTimeUpdate={setCurrentTime}
            />
          )}

          {/* Tab navigation */}
          <div className="workspace-tabs">
            {TABS.map((tab) => (
              <button
                key={tab}
                className={`workspace-tab ${activeTab === tab ? 'workspace-tab-active' : ''}`}
                onClick={() => setActiveTab(tab)}
              >
                {tab}
              </button>
            ))}
          </div>

          {/* Tab content */}
          {activeTab === 'Transcript' && (
            <TranscriptPanel
              transcript={transcript}
              loading={transcriptLoading}
              error={transcriptError}
              onRetry={fetchResults}
              currentTime={currentTime}
              onSeek={handleSeek}
              searchQuery={transcriptSearch}
              onSearchChange={setTranscriptSearch}
            />
          )}
          {activeTab === 'Summary' && (
            <SummaryPanel summary={summary} loading={summaryLoading} error={summaryError} onRetry={fetchResults} />
          )}
          {activeTab === 'Keywords' && (
            <KeywordsPanel
              keywords={keywords}
              loading={keywordsLoading}
              error={keywordsError}
              onRetry={fetchResults}
              onKeywordClick={handleKeywordClick}
            />
          )}
          {activeTab === 'Ask' && (
            <ChatPanel lectureId={lectureId} lectureReady={isCompleted} onSeek={handleSeek} />
          )}
        </>
      )}

      <ConfirmDialog
        open={confirmDelete}
        title="Delete this lecture?"
        message={`"${lecture.original_filename}" and all its transcript, summary, keywords, and indexed data will be permanently deleted.`}
        confirmLabel={deleting ? 'Deleting…' : 'Delete'}
        danger
        onConfirm={handleDelete}
        onCancel={() => setConfirmDelete(false)}
      />
    </div>
  )
}
