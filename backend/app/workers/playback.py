"""Private playback audio for lectures that have no user-uploaded original (e.g. YouTube URLs).

Uploads are played from their stored original. For other sources nothing playable would
otherwise exist, so EXTRACTING_AUDIO also stores a compact mono AAC rendition at
`{user}/{lecture}/processed/playback.m4a` in the private bucket, recorded as the lecture's
`playback` media. It is served only through short-lived signed URLs after an ownership check.

Run as a module to add playback audio to lectures processed before this existed:

    python -m app.workers.playback <lecture-id> [<lecture-id> ...]
"""

import asyncio
import hashlib
import math
import sys
import tempfile
import time
from pathlib import Path
from types import SimpleNamespace

import anyio
import httpx

from app.core.config import Settings, get_settings
from app.services.ingestion import BUCKET
from app.services.supabase_admin import ServiceSupabase
from app.workers.media import PLAYBACK_AUDIO_MIME, PLAYBACK_AUDIO_NAME, encode_playback_audio, probe


def playback_object_path(user_id: str, lecture_id: str) -> str:
    return f"{user_id}/{lecture_id}/processed/{PLAYBACK_AUDIO_NAME}"


def playback_bitrate(settings: Settings, duration_seconds: float) -> int | None:
    """Highest bitrate (kbps) up to the configured one whose output fits playback_max_bytes.

    Returns None when even the minimum bitrate wouldn't fit. 3% is kept for container overhead.
    """
    if duration_seconds <= 0:
        return settings.playback_audio_bitrate_kbps
    fitting = math.floor(settings.playback_max_bytes * 8 * 0.97 / duration_seconds / 1000)
    bitrate = min(settings.playback_audio_bitrate_kbps, fitting)
    return bitrate if bitrate >= settings.playback_min_bitrate_kbps else None


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while block := handle.read(1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


async def store_playback(
    admin: ServiceSupabase, settings: Settings, lecture: dict, source: Path, duration_seconds: float, workspace: Path
) -> dict:
    """Encode, upload and record the playback rendition. Returns details for the stage run."""
    bitrate = playback_bitrate(settings, duration_seconds)
    if bitrate is None:
        return {"playback": "skipped", "playback_reason": "too_long_for_playback_max_bytes"}

    started = time.monotonic()
    output = workspace / PLAYBACK_AUDIO_NAME
    await encode_playback_audio(settings.ffmpeg_path, source, output, bitrate, timeout=settings.ffmpeg_timeout_seconds)
    encode_ms = int((time.monotonic() - started) * 1000)
    size = output.stat().st_size
    if size > settings.playback_max_bytes:  # bitrate is an average; don't upload what storage would reject
        output.unlink(missing_ok=True)
        return {"playback": "skipped", "playback_reason": "encoded_file_too_large", "playback_bytes": size}

    info = await probe(settings.ffprobe_path, output)
    path = playback_object_path(lecture["user_id"], lecture["id"])
    started = time.monotonic()
    await admin.upload_file(BUCKET, path, output, PLAYBACK_AUDIO_MIME, upsert=True)
    upload_ms = int((time.monotonic() - started) * 1000)
    await admin.insert(
        "lecture_media",
        {
            "lecture_id": lecture["id"],
            "kind": "playback",
            "storage_path": path,
            "mime_type": PLAYBACK_AUDIO_MIME,
            "file_size": size,
            "checksum_sha256": await anyio.to_thread.run_sync(_sha256, output),
            "duration_seconds": round(info.duration_seconds or duration_seconds, 3),
            "probe": info.as_record(),
        },
        on_conflict="lecture_id,kind",
    )
    output.unlink(missing_ok=True)
    return {
        "playback": "stored",
        "playback_bytes": size,
        "playback_bitrate_kbps": bitrate,
        "playback_encode_ms": encode_ms,
        "playback_upload_ms": upload_ms,
    }


async def backfill(lecture_ids: list[str]) -> None:
    from app.workers.stages import _acquire_source  # the same source acquisition the pipeline uses

    settings = get_settings()
    async with httpx.AsyncClient(timeout=120) as http:
        admin = ServiceSupabase(http, settings)
        for lecture_id in lecture_ids:
            rows = await admin.select("lectures", {"select": "*", "id": f"eq.{lecture_id}"})
            if not rows:
                print(f"{lecture_id}: not found")
                continue
            lecture = rows[0]
            if lecture["source_type"] != "url":
                print(f"{lecture_id}: plays from its uploaded original; nothing to do")
                continue
            with tempfile.TemporaryDirectory(prefix="lecturemind-playback-", dir=settings.work_path) as directory:
                workspace = Path(directory)
                ctx = SimpleNamespace(settings=settings, lecture=lecture, admin=admin, workspace=workspace)
                source, _ = await _acquire_source(ctx)
                info = await probe(settings.ffprobe_path, source)
                details = await store_playback(admin, settings, lecture, source, info.duration_seconds or 0, workspace)
            print(f"{lecture_id}: {details}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    get_settings().work_path.mkdir(parents=True, exist_ok=True)
    asyncio.run(backfill(sys.argv[1:]))
