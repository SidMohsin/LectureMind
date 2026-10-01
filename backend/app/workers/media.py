"""Media identification (magic bytes), ffprobe inspection and FFmpeg normalization.

FFmpeg/ffprobe are always invoked with an argument list (no shell), with a
timeout, and only on paths inside the job's private workspace.
"""

import asyncio
import json
import logging
from dataclasses import dataclass
from pathlib import Path

from app.workers.lifecycle import ProcessingError

logger = logging.getLogger(__name__)

# Whisper-family models operate on 16 kHz mono audio; FLAC keeps it lossless.
TARGET_SAMPLE_RATE = 16000
TARGET_CHANNELS = 1
NORMALIZED_AUDIO_NAME = "audio.flac"
NORMALIZED_AUDIO_MIME = "audio/flac"


@dataclass(frozen=True)
class Container:
    name: str
    video_mime: str | None
    audio_mime: str | None
    extension: str


_MP4 = Container("mp4", "video/mp4", "audio/mp4", "mp4")
_MOV = Container("mov", "video/quicktime", None, "mov")
_M4A = Container("m4a", None, "audio/mp4", "m4a")
_WEBM = Container("webm", "video/webm", "audio/webm", "webm")
_MKV = Container("mkv", "video/x-matroska", None, "mkv")
_MP3 = Container("mp3", None, "audio/mpeg", "mp3")
_WAV = Container("wav", None, "audio/wav", "wav")
_OGG = Container("ogg", None, "audio/ogg", "ogg")


def sniff_container(head: bytes) -> Container | None:
    """Identify the container from the file's first bytes (never from the client's claim)."""
    if len(head) >= 12 and head[4:8] == b"ftyp":
        brand = head[8:12]
        if brand == b"qt  ":
            return _MOV
        if brand in (b"M4A ", b"M4B "):
            return _M4A
        return _MP4
    if head.startswith(b"\x1a\x45\xdf\xa3"):
        return _WEBM if b"webm" in head[:64] else _MKV
    if head.startswith(b"ID3") or (len(head) >= 2 and head[0] == 0xFF and (head[1] & 0xE0) == 0xE0):
        return _MP3
    if len(head) >= 12 and head.startswith(b"RIFF") and head[8:12] == b"WAVE":
        return _WAV
    if head.startswith(b"OggS"):
        return _OGG
    return None


def mime_for(container: Container, kind: str) -> str | None:
    """The storage MIME type for this container when submitted as `kind` (video/audio), or None if not accepted."""
    return container.video_mime if kind == "video" else container.audio_mime


@dataclass(frozen=True)
class ProbeResult:
    duration_seconds: float | None
    format_name: str | None
    has_audio: bool
    has_video: bool
    audio_codec: str | None
    sample_rate: int | None
    channels: int | None
    video_codec: str | None

    def as_record(self) -> dict:
        return {
            "format": self.format_name,
            "audio_codec": self.audio_codec,
            "sample_rate": self.sample_rate,
            "channels": self.channels,
            "video_codec": self.video_codec,
            "has_video": self.has_video,
        }


async def _run(args: list[str], timeout: float) -> tuple[int, bytes, bytes]:
    process = await asyncio.create_subprocess_exec(
        *args, stdin=asyncio.subprocess.DEVNULL, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
    )
    try:
        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=timeout)
    except asyncio.TimeoutError:
        process.kill()
        await process.wait()
        raise ProcessingError(
            "media_timeout", "Processing this media took too long.", retryable=True, details={"tool": Path(args[0]).name}
        ) from None
    except asyncio.CancelledError:
        process.kill()
        await process.wait()
        raise
    return process.returncode, stdout, stderr


def _tail(stderr: bytes, limit: int = 600) -> str:
    return stderr.decode("utf-8", errors="replace").strip()[-limit:]


async def probe(ffprobe: str, path: Path, timeout: float = 120) -> ProbeResult:
    code, stdout, stderr = await _run(
        [ffprobe, "-v", "error", "-print_format", "json", "-show_format", "-show_streams", str(path)], timeout
    )
    if code != 0:
        raise ProcessingError(
            "media_unreadable",
            "This file couldn't be read as audio or video. It may be corrupted or incomplete.",
            details={"ffprobe": _tail(stderr)},
        )
    try:
        data = json.loads(stdout)
    except json.JSONDecodeError:
        raise ProcessingError("media_unreadable", "This file couldn't be read as audio or video.") from None

    streams = data.get("streams", [])
    audio = next((s for s in streams if s.get("codec_type") == "audio"), None)
    video = next((s for s in streams if s.get("codec_type") == "video" and not s.get("disposition", {}).get("attached_pic")), None)
    raw_duration = data.get("format", {}).get("duration") or (audio or {}).get("duration")
    try:
        duration = float(raw_duration) if raw_duration is not None else None
    except ValueError:
        duration = None

    return ProbeResult(
        duration_seconds=duration,
        format_name=data.get("format", {}).get("format_name"),
        has_audio=audio is not None,
        has_video=video is not None,
        audio_codec=(audio or {}).get("codec_name"),
        sample_rate=int(audio["sample_rate"]) if audio and audio.get("sample_rate") else None,
        channels=(audio or {}).get("channels"),
        video_codec=(video or {}).get("codec_name"),
    )


def validate_input(result: ProbeResult, max_duration_seconds: int) -> None:
    if not result.has_audio:
        raise ProcessingError("no_audio_stream", "This file has no audio track, so there's nothing to transcribe.")
    if not result.duration_seconds or result.duration_seconds <= 0:
        raise ProcessingError("media_unreadable", "This file's duration couldn't be determined. It may be corrupted.")
    if result.duration_seconds > max_duration_seconds:
        hours = max_duration_seconds / 3600
        raise ProcessingError(
            "media_too_long",
            f"This recording is longer than the {hours:g}-hour limit.",
            details={"duration_seconds": result.duration_seconds},
        )


async def normalize_audio(ffmpeg: str, source: Path, destination: Path, timeout: float) -> None:
    """Extract the first audio stream as 16 kHz mono 16-bit FLAC."""
    args = [
        ffmpeg, "-nostdin", "-hide_banner", "-loglevel", "error", "-y",
        "-i", str(source),
        "-map", "0:a:0", "-vn",
        "-ac", str(TARGET_CHANNELS), "-ar", str(TARGET_SAMPLE_RATE), "-sample_fmt", "s16",
        "-c:a", "flac",
        str(destination),
    ]  # fmt: skip
    code, _, stderr = await _run(args, timeout)
    if code != 0 or not destination.exists() or destination.stat().st_size == 0:
        raise ProcessingError(
            "audio_extraction_failed",
            "The audio couldn't be extracted from this file. It may be corrupted.",
            details={"ffmpeg": _tail(stderr), "exit_code": code},
        )


PLAYBACK_AUDIO_NAME = "playback.m4a"
PLAYBACK_AUDIO_MIME = "audio/mp4"


async def encode_playback_audio(ffmpeg: str, source: Path, destination: Path, bitrate_kbps: int, timeout: float) -> None:
    """Encode the first audio stream as mono AAC in MP4 for in-browser playback.

    `+faststart` puts the index at the front so playback and seeking can begin
    before the whole file has downloaded (with HTTP range requests).
    """
    args = [
        ffmpeg, "-nostdin", "-hide_banner", "-loglevel", "error", "-y",
        "-i", str(source),
        "-map", "0:a:0", "-vn", "-ac", "1",
        "-c:a", "aac", "-b:a", f"{bitrate_kbps}k",
        "-movflags", "+faststart",
        str(destination),
    ]  # fmt: skip
    code, _, stderr = await _run(args, timeout)
    if code != 0 or not destination.exists() or destination.stat().st_size == 0:
        raise ProcessingError(
            "playback_encoding_failed",
            "The lecture's audio couldn't be prepared for playback.",
            details={"ffmpeg": _tail(stderr), "exit_code": code},
        )
