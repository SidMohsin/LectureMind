"""Small media files generated with FFmpeg at test time (nothing binary is committed)."""

import subprocess
from pathlib import Path

import pytest

from .fakes import ffmpeg_available

requires_ffmpeg = pytest.mark.skipif(not ffmpeg_available(), reason="ffmpeg/ffprobe not installed")


def _ffmpeg(*args: str) -> None:
    subprocess.run(["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", "-y", *args], check=True)


@pytest.fixture(scope="session")
def media(tmp_path_factory) -> dict[str, Path]:
    if not ffmpeg_available():
        pytest.skip("ffmpeg/ffprobe not installed")
    root = tmp_path_factory.mktemp("media")
    files = {
        "mp3": root / "tone.mp3",
        "wav": root / "tone.wav",
        "mp4": root / "lecture.mp4",
        "video_only": root / "silent.mp4",
        "corrupt": root / "corrupt.mp4",
    }
    _ffmpeg("-f", "lavfi", "-i", "sine=frequency=440:duration=3:sample_rate=44100", "-ac", "2", str(files["mp3"]))
    _ffmpeg("-f", "lavfi", "-i", "sine=frequency=330:duration=2:sample_rate=48000", str(files["wav"]))
    _ffmpeg(
        "-f", "lavfi", "-i", "testsrc=duration=3:size=160x120:rate=10",
        "-f", "lavfi", "-i", "sine=frequency=550:duration=3",
        "-shortest", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", str(files["mp4"]),
    )  # fmt: skip
    _ffmpeg("-f", "lavfi", "-i", "testsrc=duration=2:size=160x120:rate=10", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(files["video_only"]))
    # Valid MP4 signature, truncated garbage afterwards: passes the sniff, fails ffprobe.
    files["corrupt"].write_bytes(files["mp4"].read_bytes()[:40] + b"\x00garbage" * 200)
    return files
