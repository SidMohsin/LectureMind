import { forwardRef, useImperativeHandle, useRef } from 'react'
import { mediaUrl } from '../services/api'

// Real HTML5 media element backed by the backend's Range-enabled
// /api/lectures/{id}/media endpoint. Exposes an imperative `seek(seconds)`
// method via ref so transcript/chat timestamp clicks can jump playback,
// and reports currentTime upward so the transcript can highlight in sync.

const MediaPlayer = forwardRef(function MediaPlayer({ lectureId, fileType, onTimeUpdate }, ref) {
  const elRef = useRef(null)

  useImperativeHandle(ref, () => ({
    seek(seconds) {
      const el = elRef.current
      if (!el) return
      el.currentTime = seconds
      el.play().catch(() => {
        // Autoplay may be blocked by the browser — the seek itself still
        // succeeds and the user can press play manually.
      })
    },
  }))

  function handleTimeUpdate(e) {
    if (onTimeUpdate) onTimeUpdate(e.target.currentTime)
  }

  const src = mediaUrl(lectureId)

  if (fileType === 'video') {
    return (
      <div className="media-player-wrapper">
        <video
          ref={elRef}
          className="media-player-video"
          src={src}
          controls
          preload="metadata"
          onTimeUpdate={handleTimeUpdate}
        >
          Your browser does not support HTML5 video playback.
        </video>
      </div>
    )
  }

  return (
    <div className="media-player-wrapper media-player-audio-wrapper">
      <div className="media-player-audio-icon" aria-hidden="true">♪</div>
      <audio
        ref={elRef}
        className="media-player-audio"
        src={src}
        controls
        preload="metadata"
        onTimeUpdate={handleTimeUpdate}
      >
        Your browser does not support HTML5 audio playback.
      </audio>
    </div>
  )
})

export default MediaPlayer
