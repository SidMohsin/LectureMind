"""
Speech-to-text service using faster-whisper.

faster-whisper is a CTranslate2 reimplementation of OpenAI Whisper that is
significantly faster and lighter on CPU, which makes it practical to run on
a normal student laptop without a GPU.
"""
from typing import List, Dict
from functools import lru_cache
from app.config import settings


class TranscriptionError(Exception):
    pass


@lru_cache(maxsize=1)
def _get_model():
    """
    Lazily load and cache the faster-whisper model so it is only loaded once
    per backend process (loading is the slowest part of using Whisper).
    """
    try:
        from faster_whisper import WhisperModel
    except ImportError as e:
        raise TranscriptionError(
            "faster-whisper is not installed. Run: pip install faster-whisper"
        ) from e

    try:
        model = WhisperModel(
            settings.WHISPER_MODEL_SIZE,
            device=settings.WHISPER_DEVICE,
            compute_type=settings.WHISPER_COMPUTE_TYPE,
        )
    except Exception as e:
        raise TranscriptionError(f"Failed to load Whisper model '{settings.WHISPER_MODEL_SIZE}': {e}") from e

    return model


def transcribe_audio(audio_path: str) -> Dict:
    """
    Transcribe the given audio file and return a dict:
    {
        "language": "en",
        "segments": [{"start": float, "end": float, "text": str}, ...],
        "full_text": str
    }
    Timestamps (start/end) for each segment are preserved as returned by Whisper.
    """
    model = _get_model()

    try:
        segments_iter, info = model.transcribe(
            audio_path,
            beam_size=5,
            vad_filter=True,  # filters out silence, improves segment quality
        )
    except Exception as e:
        raise TranscriptionError(f"Whisper transcription failed: {e}") from e

    segments: List[Dict] = []
    full_text_parts = []
    for seg in segments_iter:
        text = seg.text.strip()
        if not text:
            continue
        segments.append({
            "start": round(float(seg.start), 2),
            "end": round(float(seg.end), 2),
            "text": text,
        })
        full_text_parts.append(text)

    if not segments:
        raise TranscriptionError(
            "Transcription produced no speech segments. The audio may be silent, "
            "too short, or in an unsupported format."
        )

    return {
        "language": getattr(info, "language", None),
        "segments": segments,
        "full_text": " ".join(full_text_parts),
    }
