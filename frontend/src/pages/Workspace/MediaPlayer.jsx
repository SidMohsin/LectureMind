import { forwardRef, useCallback, useEffect, useImperativeHandle, useRef, useState } from "react";
import { getMedia } from "../../services/workspace";
import {
  AlertIcon,
  BackIcon,
  ForwardIcon,
  FullscreenIcon,
  MuteIcon,
  PauseIcon,
  PlayIcon,
  RefreshIcon,
  VolumeIcon,
} from "../../components/ui/icons";
import { findChapterIndex, formatClock } from "../../workspace/timeline";
import "./MediaPlayer.css";

const RATES = [1, 1.25, 1.5, 2];

/**
 * Plays the lecture's private media from a short-lived signed URL (fetched from the
 * API after an ownership check). The browser streams it with HTTP range requests, so
 * seeking doesn't download the whole file. Exposes seek(seconds, { play }) to the page.
 */
const MediaPlayer = forwardRef(function MediaPlayer({ lectureId, chapters, fallbackDuration, onTimeUpdate }, ref) {
  const containerRef = useRef(null);
  const mediaRef = useRef(null);
  const pendingSeek = useRef(null);
  const renewedUrl = useRef(false);

  const [media, setMedia] = useState(null);
  const [phase, setPhase] = useState("fetching"); // fetching | loading | ready | error | unavailable
  const [errorMessage, setErrorMessage] = useState("");
  const [playing, setPlaying] = useState(false);
  const [buffering, setBuffering] = useState(false);
  const [current, setCurrent] = useState(0);
  const [duration, setDuration] = useState(fallbackDuration || 0);
  const [volume, setVolume] = useState(1);
  const [muted, setMuted] = useState(false);
  const [rate, setRate] = useState(1);
  const [fullscreen, setFullscreen] = useState(false);

  const loadMedia = useCallback(
    async (resumeAt) => {
      setPhase("fetching");
      try {
        const access = await getMedia(lectureId);
        if (resumeAt !== undefined) pendingSeek.current = { time: resumeAt, play: false };
        setMedia(access);
        setPhase("loading");
      } catch (error) {
        if (error.status === 404) {
          setPhase("unavailable");
        } else {
          setErrorMessage(error.message || "The lecture media couldn't be loaded.");
          setPhase("error");
        }
      }
    },
    [lectureId]
  );

  useEffect(() => {
    loadMedia();
  }, [loadMedia]);

  const seek = useCallback((time, { play = false } = {}) => {
    const element = mediaRef.current;
    if (!element || element.readyState < 1) {
      pendingSeek.current = { time, play };
      return;
    }
    const limit = Number.isFinite(element.duration) ? element.duration : time;
    element.currentTime = Math.max(0, Math.min(time, limit));
    setCurrent(element.currentTime);
    onTimeUpdate?.(element.currentTime);
    if (play) element.play().catch(() => {});
  }, [onTimeUpdate]);

  useImperativeHandle(ref, () => ({ seek }), [seek]);

  useEffect(() => {
    const onChange = () => setFullscreen(document.fullscreenElement === containerRef.current);
    document.addEventListener("fullscreenchange", onChange);
    return () => document.removeEventListener("fullscreenchange", onChange);
  }, []);

  const handlers = {
    onLoadedMetadata: (event) => {
      const element = event.currentTarget;
      if (Number.isFinite(element.duration)) setDuration(element.duration);
      element.volume = volume;
      element.muted = muted;
      element.playbackRate = rate;
      setPhase("ready");
      if (pendingSeek.current) {
        const { time, play } = pendingSeek.current;
        pendingSeek.current = null;
        seek(time, { play });
      }
    },
    onTimeUpdate: (event) => {
      setCurrent(event.currentTarget.currentTime);
      onTimeUpdate?.(event.currentTarget.currentTime);
    },
    onPlay: () => setPlaying(true),
    onPause: () => setPlaying(false),
    onEnded: () => setPlaying(false),
    onWaiting: () => setBuffering(true),
    onPlaying: () => setBuffering(false),
    onCanPlay: () => setBuffering(false),
    onError: () => {
      // Signed URLs expire; renew once and resume where playback was.
      if (!renewedUrl.current) {
        renewedUrl.current = true;
        loadMedia(mediaRef.current?.currentTime || current);
        return;
      }
      setPlaying(false);
      setErrorMessage("This lecture's media couldn't be played. Your browser may not support its format.");
      setPhase("error");
    },
  };

  const togglePlay = () => {
    const element = mediaRef.current;
    if (!element || phase !== "ready") return;
    if (element.paused) element.play().catch(() => {});
    else element.pause();
  };
  const skip = (delta) => seek((mediaRef.current?.currentTime || 0) + delta);
  const changeVolume = (value) => {
    const element = mediaRef.current;
    setVolume(value);
    setMuted(value === 0);
    if (element) {
      element.volume = value;
      element.muted = value === 0;
    }
  };
  const toggleMute = () => {
    const next = !muted;
    setMuted(next);
    if (mediaRef.current) mediaRef.current.muted = next;
  };
  const changeRate = (value) => {
    setRate(value);
    if (mediaRef.current) mediaRef.current.playbackRate = value;
  };
  const toggleFullscreen = () => {
    if (document.fullscreenElement) document.exitFullscreen?.();
    else containerRef.current?.requestFullscreen?.().catch(() => {});
  };

  const onKeyDown = (event) => {
    if (event.target.closest("input, select, textarea") || event.metaKey || event.ctrlKey || event.altKey) return;
    const actions = {
      " ": togglePlay,
      k: togglePlay,
      ArrowLeft: () => skip(-5),
      ArrowRight: () => skip(5),
      j: () => skip(-10),
      l: () => skip(10),
      m: toggleMute,
      f: () => isVideo && toggleFullscreen(),
    };
    const action = actions[event.key];
    if (action) {
      event.preventDefault();
      action();
    }
  };

  const isVideo = media?.kind === "video";
  const total = duration || fallbackDuration || 0;
  const chapterIndex = findChapterIndex(chapters, current);
  const chapter = chapterIndex >= 0 ? chapters[chapterIndex] : null;
  const ready = phase === "ready";
  const MediaTag = isVideo ? "video" : "audio";

  return (
    <section
      className={`player ${isVideo ? "player--video" : "player--audio"} ${fullscreen ? "player--fullscreen" : ""}`}
      ref={containerRef}
      onKeyDown={onKeyDown}
      aria-label="Lecture player"
    >
      {chapter && (
        <p className="player__chapter">
          <span className="player__chapter-dot" aria-hidden="true" />
          Chapter {chapter.sequence + 1}: {chapter.title}
          <span className="player__chapter-time mono">
            {formatClock(chapter.start_seconds)} – {formatClock(chapter.end_seconds)}
          </span>
        </p>
      )}

      <div className="player__stage">
        {media && (
          <MediaTag
            ref={mediaRef}
            className="player__media"
            src={media.url}
            preload="metadata"
            playsInline
            onClick={togglePlay}
            {...handlers}
          />
        )}
        {!isVideo && (phase === "ready" || phase === "loading") && (
          <div className="player__audio-card">
            <p className="player__audio-label mono">Lecture audio</p>
            <p className="player__audio-title">{chapter ? chapter.title : "Lecture"}</p>
            {chapter?.description && <p className="player__audio-description">{chapter.description}</p>}
          </div>
        )}
        {(phase === "fetching" || phase === "loading" || (ready && buffering)) && (
          <div className="player__overlay" role="status">
            <span className="player__spinner" aria-hidden="true" />
            <span>{phase === "ready" ? "Buffering…" : "Loading lecture media…"}</span>
          </div>
        )}
        {phase === "error" && (
          <div className="player__overlay player__overlay--error" role="alert">
            <AlertIcon size={20} />
            <span>{errorMessage}</span>
            <button
              type="button"
              className="player__retry"
              onClick={() => {
                renewedUrl.current = false;
                loadMedia(current);
              }}
            >
              <RefreshIcon size={14} /> Retry
            </button>
          </div>
        )}
        {phase === "unavailable" && (
          <div className="player__overlay player__overlay--muted" role="status">
            <span>Playback isn’t available for this lecture. The transcript and lecture intelligence still work.</span>
          </div>
        )}
      </div>

      <div className="player__controls">
        <div className="player__timeline">
          <input
            type="range"
            className="player__seek"
            min={0}
            max={Math.max(total, 1)}
            step={1}
            value={Math.min(current, total || current)}
            disabled={!ready}
            onChange={(event) => seek(Number(event.target.value))}
            aria-label="Seek"
            aria-valuetext={`${formatClock(current)} of ${formatClock(total)}`}
            style={{ "--progress": `${total ? (Math.min(current, total) / total) * 100 : 0}%` }}
          />
          {total > 0 &&
            chapters.slice(1).map((item) => (
              <span
                key={item.sequence}
                className="player__marker"
                style={{ left: `${(item.start_seconds / total) * 100}%` }}
                aria-hidden="true"
              />
            ))}
        </div>

        <div className="player__buttons">
          <button type="button" className="player__play" onClick={togglePlay} disabled={!ready} aria-label={playing ? "Pause" : "Play"}>
            {playing ? <PauseIcon size={18} /> : <PlayIcon size={18} />}
          </button>
          <button type="button" className="player__icon" onClick={() => skip(-10)} disabled={!ready} aria-label="Back 10 seconds">
            <BackIcon size={18} />
          </button>
          <button type="button" className="player__icon" onClick={() => skip(10)} disabled={!ready} aria-label="Forward 10 seconds">
            <ForwardIcon size={18} />
          </button>
          <p className="player__time mono" aria-live="off">
            <span className="player__time-current">{formatClock(current)}</span> / {formatClock(total)}
          </p>

          <div className="player__right">
            <div className="player__volume">
              <button type="button" className="player__icon" onClick={toggleMute} disabled={!ready} aria-label={muted ? "Unmute" : "Mute"}>
                {muted ? <MuteIcon size={18} /> : <VolumeIcon size={18} />}
              </button>
              <input
                type="range"
                min={0}
                max={1}
                step={0.05}
                value={muted ? 0 : volume}
                disabled={!ready}
                onChange={(event) => changeVolume(Number(event.target.value))}
                aria-label="Volume"
                style={{ "--progress": `${(muted ? 0 : volume) * 100}%` }}
              />
            </div>
            <div className="player__rates" role="group" aria-label="Playback speed">
              {RATES.map((value) => (
                <button
                  key={value}
                  type="button"
                  className="player__rate mono"
                  aria-pressed={rate === value}
                  disabled={!ready}
                  onClick={() => changeRate(value)}
                >
                  {value}×
                </button>
              ))}
            </div>
            {isVideo && (
              <button
                type="button"
                className="player__icon"
                onClick={toggleFullscreen}
                disabled={!ready}
                aria-label={fullscreen ? "Exit full screen" : "Full screen"}
              >
                <FullscreenIcon size={18} />
              </button>
            )}
          </div>
        </div>
      </div>
    </section>
  );
});

export default MediaPlayer;
