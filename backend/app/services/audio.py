"""
Audio extraction service.

Uses FFmpeg (via subprocess) to extract a standardised mono 16kHz WAV audio
track from an uploaded video, or to re-encode an uploaded audio file into
the same standard format so that Whisper receives consistent input.
"""
import subprocess
import shutil
import os


class AudioExtractionError(Exception):
    pass


def check_ffmpeg_available() -> bool:
    return shutil.which("ffmpeg") is not None


def extract_audio(input_path: str, output_path: str) -> str:
    """
    Extract/convert audio from input_path (video or audio) into a standard
    16kHz mono PCM WAV file at output_path using FFmpeg.
    """
    if not check_ffmpeg_available():
        raise AudioExtractionError(
            "FFmpeg was not found on this system. Please install FFmpeg and ensure "
            "it is available on your PATH (see README installation instructions)."
        )

    if not os.path.exists(input_path):
        raise AudioExtractionError(f"Input media file not found: {input_path}")

    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    cmd = [
        "ffmpeg",
        "-y",  # overwrite output
        "-i", input_path,
        "-vn",  # no video
        "-acodec", "pcm_s16le",
        "-ar", "16000",  # 16kHz sample rate, standard for Whisper
        "-ac", "1",  # mono
        output_path,
    ]

    try:
        result = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=1800,
        )
    except subprocess.TimeoutExpired:
        raise AudioExtractionError("Audio extraction timed out. The media file may be too large or corrupted.")

    if result.returncode != 0:
        stderr_tail = result.stderr.decode(errors="ignore")[-800:]
        raise AudioExtractionError(f"FFmpeg failed to extract audio. Details: {stderr_tail}")

    if not os.path.exists(output_path) or os.path.getsize(output_path) == 0:
        raise AudioExtractionError("Audio extraction produced an empty file. The source media may be corrupted.")

    return output_path


def get_media_duration_seconds(input_path: str) -> float:
    """Use ffprobe to get duration of a media file. Returns 0.0 if unavailable."""
    if shutil.which("ffprobe") is None:
        return 0.0
    cmd = [
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        input_path,
    ]
    try:
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=60)
        if result.returncode == 0:
            return float(result.stdout.decode().strip())
    except Exception:
        pass
    return 0.0
