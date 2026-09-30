"""Lifecycle rules, media identification/FFmpeg, workspaces and the Redis queue."""

import os
import time

import fakeredis.aioredis
import pytest

from app.services.queue import RedisJobQueue
from app.workers import lifecycle
from app.workers.lifecycle import ProcessingError
from app.workers.media import mime_for, normalize_audio, probe, sniff_container, validate_input
from app.workers.workspace import job_workspace, remove_stale_workspaces

from .media_fixtures import media, requires_ffmpeg  # noqa: F401 - fixture import

pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend():
    return "asyncio"


# --- lifecycle ------------------------------------------------------------------------


def test_lecture_lifecycle_follows_the_documented_order():
    path = ["UPLOADED", "QUEUED", *lifecycle.PIPELINE_STAGES, "READY"]
    for current, target in zip(path, path[1:]):
        assert lifecycle.can_transition_lecture(current, target), (current, target)


@pytest.mark.parametrize(
    "current,target",
    [
        ("UPLOADED", "READY"),  # skipping the pipeline
        ("QUEUED", "READY"),
        ("EXTRACTING_AUDIO", "CHUNKING"),  # skipping stages
        ("TRANSCRIBING", "EXTRACTING_AUDIO"),  # going backwards
        ("READY", "FAILED"),
        ("READY", "QUEUED"),
        ("FAILED", "READY"),
        ("UPLOADED", "UPLOADED"),
    ],
)
def test_invalid_lecture_transitions_are_rejected(current, target):
    assert not lifecycle.can_transition_lecture(current, target)
    with pytest.raises(lifecycle.InvalidTransition):
        lifecycle.require_lecture_transition(current, target)


def test_failure_and_retry_transitions():
    for stage in ("QUEUED", *lifecycle.PIPELINE_STAGES):
        assert lifecycle.can_transition_lecture(stage, "FAILED")
    assert lifecycle.can_transition_lecture("FAILED", "QUEUED")


def test_job_transitions():
    assert lifecycle.can_transition_job("queued", "running")
    assert lifecycle.can_transition_job("running", "waiting")
    assert lifecycle.can_transition_job("waiting", "queued")
    assert lifecycle.can_transition_job("failed", "queued")
    assert not lifecycle.can_transition_job("queued", "succeeded")
    assert not lifecycle.can_transition_job("succeeded", "queued")
    assert not lifecycle.can_transition_job("waiting", "running")


def test_next_stage_ends_after_intelligence():
    assert lifecycle.next_stage("EXTRACTING_AUDIO") == "TRANSCRIBING"
    assert lifecycle.next_stage("GENERATING_INTELLIGENCE") is None


# --- magic-byte sniffing ------------------------------------------------------------------


@pytest.mark.parametrize(
    "head,kind,expected",
    [
        (b"\x00\x00\x00\x20ftypisom" + b"\0" * 8, "video", "video/mp4"),
        (b"\x00\x00\x00\x14ftypqt  " + b"\0" * 8, "video", "video/quicktime"),
        (b"\x00\x00\x00\x20ftypM4A " + b"\0" * 8, "audio", "audio/mp4"),
        (b"\x1a\x45\xdf\xa3" + b"\0" * 20 + b"webm", "video", "video/webm"),
        (b"\x1a\x45\xdf\xa3" + b"\0" * 20 + b"matroska", "video", "video/x-matroska"),
        (b"ID3\x04\x00" + b"\0" * 10, "audio", "audio/mpeg"),
        (b"RIFF\x24\x00\x00\x00WAVEfmt ", "audio", "audio/wav"),
        (b"OggS\x00\x02" + b"\0" * 10, "audio", "audio/ogg"),
    ],
)
def test_container_is_identified_from_bytes(head, kind, expected):
    assert mime_for(sniff_container(head), kind) == expected


def test_mismatched_or_unknown_content_is_not_accepted():
    assert sniff_container(b"%PDF-1.7\n") is None
    assert sniff_container(b"<html><script>") is None
    assert mime_for(sniff_container(b"ID3\x04" + b"\0" * 12), "video") is None  # MP3 sent as video
    assert mime_for(sniff_container(b"\x00\x00\x00\x14ftypqt  " + b"\0" * 8), "audio") is None


# --- ffprobe / FFmpeg (real binaries) ---------------------------------------------------------


@requires_ffmpeg
async def test_probe_reads_real_media(media):
    video = await probe("ffprobe", media["mp4"])
    assert video.has_audio and video.has_video
    assert 2.5 < video.duration_seconds < 3.5
    audio = await probe("ffprobe", media["mp3"])
    assert audio.has_audio and not audio.has_video and audio.channels == 2


@requires_ffmpeg
async def test_corrupted_media_fails_cleanly(media):
    with pytest.raises(ProcessingError) as caught:
        await probe("ffprobe", media["corrupt"])
    assert caught.value.code == "media_unreadable"
    assert caught.value.retryable is False
    assert "ffprobe" in caught.value.details


@requires_ffmpeg
async def test_video_without_audio_is_rejected(media):
    result = await probe("ffprobe", media["video_only"])
    with pytest.raises(ProcessingError) as caught:
        validate_input(result, max_duration_seconds=3600)
    assert caught.value.code == "no_audio_stream"


@requires_ffmpeg
async def test_overlong_media_is_rejected(media):
    result = await probe("ffprobe", media["mp3"])
    with pytest.raises(ProcessingError) as caught:
        validate_input(result, max_duration_seconds=1)
    assert caught.value.code == "media_too_long"


@requires_ffmpeg
@pytest.mark.parametrize("name", ["mp4", "mp3", "wav"])
async def test_audio_is_normalized_to_16k_mono_flac(media, tmp_path, name):
    output = tmp_path / "audio.flac"
    await normalize_audio("ffmpeg", media[name], output, timeout=60)
    result = await probe("ffprobe", output)
    assert (result.audio_codec, result.sample_rate, result.channels) == ("flac", 16000, 1)
    assert not result.has_video


@requires_ffmpeg
async def test_ffmpeg_failure_is_reported(media, tmp_path):
    with pytest.raises(ProcessingError) as caught:
        await normalize_audio("ffmpeg", media["video_only"], tmp_path / "audio.flac", timeout=60)
    assert caught.value.code == "audio_extraction_failed"
    assert "exit_code" in caught.value.details


async def test_missing_ffmpeg_binary_does_not_use_a_shell(tmp_path):
    # An argument list with shell metacharacters must be treated as a literal (non-existent) path.
    with pytest.raises((FileNotFoundError, ProcessingError)):
        await probe("ffprobe-does-not-exist", tmp_path / "x; rm -rf /")


# --- workspaces ------------------------------------------------------------------------------


def test_workspace_is_private_and_removed_after_success(tmp_path):
    job_id = "8a6d8b8e-5a1f-4c1e-9d1a-2b3c4d5e6f70"
    with job_workspace(tmp_path, job_id) as first, job_workspace(tmp_path, job_id) as second:
        assert first != second  # two runs never share files
        (first / "big.bin").write_bytes(b"x" * 1024)
    assert not first.exists() and not second.exists()


def test_workspace_is_removed_after_failure(tmp_path):
    with pytest.raises(RuntimeError):
        with job_workspace(tmp_path, "8a6d8b8e-5a1f-4c1e-9d1a-2b3c4d5e6f70") as path:
            (path / "partial.flac").write_bytes(b"x")
            raise RuntimeError("boom")
    assert list(tmp_path.iterdir()) == []


def test_stale_workspaces_from_crashed_workers_are_removed(tmp_path):
    stale = tmp_path / "job-old"
    fresh = tmp_path / "job-new"
    other = tmp_path / "not-a-job"
    for path in (stale, fresh, other):
        path.mkdir()
    old = time.time() - 7200
    os.utime(stale, (old, old))
    os.utime(other, (old, old))
    assert remove_stale_workspaces(tmp_path, older_than_seconds=3600) == 1
    assert not stale.exists() and fresh.exists() and other.exists()


# --- Redis queue -------------------------------------------------------------------------------


async def test_redis_queue_is_fifo_and_dedupes_sweep_notifications():
    queue = RedisJobQueue("redis://localhost:6379/0", "test-queue")
    queue._redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    await queue.enqueue("a")
    await queue.enqueue("b")
    await queue.enqueue("c", dedupe_seconds=30)
    await queue.enqueue("c", dedupe_seconds=30)  # suppressed
    assert [await queue.dequeue(1) for _ in range(4)] == ["a", "b", "c", None]
