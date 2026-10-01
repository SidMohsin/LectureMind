"""Speech-to-text behind a small interface, implemented with faster-whisper.

faster-whisper runs Whisper models on CTranslate2 (no PyTorch). The loaded model
is cached per worker process. Transcription is CPU/GPU-bound and blocking, so
callers run it in a thread; progress is reported through a shared object that
the async side reads, and a `cancelled` flag lets the caller stop it early.
"""

import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from app.core.config import Settings


@dataclass(frozen=True)
class TranscribedSegment:
    start: float
    end: float
    text: str
    avg_logprob: float | None
    no_speech_prob: float | None


@dataclass
class Transcript:
    language: str | None
    language_probability: float | None
    duration_seconds: float
    segments: list[TranscribedSegment]
    model: str
    model_config: dict


@dataclass
class TranscriptionProgress:
    """Written by the transcription thread, read by the async side."""

    processed_seconds: float = 0.0
    total_seconds: float = 0.0
    cancelled: bool = False


class TranscriptionCancelled(Exception):
    pass


class Transcriber(Protocol):
    def transcribe(self, audio: Path, progress: TranscriptionProgress) -> Transcript: ...


_models: dict[tuple, object] = {}
_models_lock = threading.Lock()

SAMPLE_RATE = 16000


def decode_audio(path: Path, ffmpeg: str) -> "numpy.ndarray":  # noqa: F821
    """Decode to 16 kHz mono float32 samples with FFmpeg.

    faster-whisper's own decoder depends on PyAV, whose newer releases are
    incompatible with it; FFmpeg is already required by the pipeline and is the
    same decoder used for audio extraction.
    """
    import subprocess

    import numpy

    result = subprocess.run(
        [ffmpeg, "-nostdin", "-hide_banner", "-loglevel", "error", "-i", str(path),
         "-f", "f32le", "-acodec", "pcm_f32le", "-ac", "1", "-ar", str(SAMPLE_RATE), "-"],
        capture_output=True,
        check=False,
    )  # fmt: skip
    if result.returncode != 0 or not result.stdout:
        raise RuntimeError(f"FFmpeg could not decode the audio: {result.stderr.decode(errors='replace')[-300:]}")
    return numpy.frombuffer(result.stdout, dtype=numpy.float32)


class FasterWhisperTranscriber:
    def __init__(self, settings: Settings):
        self.model_name = settings.transcription_model
        self.device = settings.transcription_device
        self.compute_type = settings.transcription_compute_type
        self.beam_size = settings.transcription_beam_size
        self.language = settings.transcription_language or None
        self.cache_dir = settings.model_cache_path / "whisper"
        self.ffmpeg = settings.ffmpeg_path

    def config(self) -> dict:
        import faster_whisper

        return {
            "implementation": "faster-whisper",
            "implementation_version": faster_whisper.__version__,
            "model": self.model_name,
            "device": self.device,
            "compute_type": self.compute_type,
            "beam_size": self.beam_size,
            "language": self.language or "auto",
            "vad_filter": True,
            "condition_on_previous_text": False,
        }

    def _model(self):
        from faster_whisper import WhisperModel

        key = (self.model_name, self.device, self.compute_type)
        with _models_lock:
            if key not in _models:
                self.cache_dir.mkdir(parents=True, exist_ok=True)
                _models[key] = WhisperModel(
                    self.model_name, device=self.device, compute_type=self.compute_type, download_root=str(self.cache_dir)
                )
            return _models[key]

    def transcribe(self, audio: Path, progress: TranscriptionProgress) -> Transcript:
        samples = decode_audio(audio, self.ffmpeg)
        segments_iter, info = self._model().transcribe(
            samples,
            beam_size=self.beam_size,
            language=self.language,
            vad_filter=True,
            # Prevents Whisper's run-on repetition loops from propagating across segments.
            condition_on_previous_text=False,
        )
        progress.total_seconds = info.duration
        segments: list[TranscribedSegment] = []
        for segment in segments_iter:  # decoding happens lazily, segment by segment
            if progress.cancelled:
                raise TranscriptionCancelled()
            segments.append(
                TranscribedSegment(
                    start=round(segment.start, 3),
                    end=round(max(segment.end, segment.start), 3),
                    text=segment.text,
                    avg_logprob=segment.avg_logprob,
                    no_speech_prob=segment.no_speech_prob,
                )
            )
            progress.processed_seconds = segment.end
        return Transcript(
            language=info.language,
            language_probability=info.language_probability,
            duration_seconds=info.duration,
            segments=segments,
            model=f"faster-whisper/{self.model_name}",
            model_config=self.config(),
        )
