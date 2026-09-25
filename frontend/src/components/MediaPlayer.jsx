import { forwardRef, useImperativeHandle, useRef } from 'react'
import { mediaUrl } from '../services/api'
import { getStoredToken } from '../services/api'

const MediaPlayer = forwardRef(function MediaPlayer({ lectureId, fileType, onTimeUpdate }, ref) {
  const elRef = useRef(null)

  useImperativeHandle(ref, () => ({
    seek(seconds) {
      const el = elRef.current
      if (!el) return
      el.currentTime = seconds
      el.play().catch(() => {})
    },
  }))

  function handleTimeUpdate(e) {
    if (onTimeUpdate) onTimeUpdate(e.target.currentTime)
  }

  // Append JWT token as query param since <video>/<audio> src can't pass headers
  const token = getStoredToken()
  const src = `${mediaUrl(lectureId)}${token ? `?token=${encodeURIComponent(token)}` : ''}`

  if (fileType === 'video') {
    return (
      <div className="media-area">
        <video
          ref={elRef}
          className="media-player-video"
          src={src}
          controls
          preload="metadata"
          onTimeUpdate={handleTimeUpdate}
        >
          Your browser does not support HTML5 video.
        </video>
      </div>
    )
  }

  return (
    <div className="media-area">
      <div className="media-player-audio-wrapper">
        <div className="media-player-audio-icon" aria-hidden="true">♪</div>
        <audio
          ref={elRef}
          className="media-player-audio"
          src={src}
          controls
          preload="metadata"
          onTimeUpdate={handleTimeUpdate}
        >
          Your browser does not support HTML5 audio.
        </audio>
      </div>
    </div>
  )
})

export default MediaPlayer
