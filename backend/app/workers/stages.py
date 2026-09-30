"""Stage implementations. Each takes the job context and returns details recorded on its stage run.

Storage policy: only user-provided source media (the original upload) is persisted in
Supabase Storage. Derived audio is a temporary artifact of the worker: it is written
to the job's private workspace, consumed by the stages that need it, and deleted with
the workspace when the run ends (success or failure).
"""

import hashlib
import time

import anyio

from app.services.ingestion import BUCKET
from app.services.sources import provider_named
from app.services.supabase_admin import StorageObjectTooLarge
from app.workers.context import AudioArtifact, JobContext
from app.workers.lifecycle import ProcessingError
from app.workers.media import NORMALIZED_AUDIO_NAME, TARGET_CHANNELS, TARGET_SAMPLE_RATE, normalize_audio, probe, validate_input


def _sha256(path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while block := handle.read(1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


async def _acquire_source(ctx: JobContext):
    """Put the lecture's source media in the workspace. Returns (path, stored original media row or None)."""
    settings, lecture = ctx.settings, ctx.lecture
    if lecture["source_type"] in ("video", "audio"):
        rows = await ctx.admin.select(
            "lecture_media", {"select": "*", "lecture_id": f"eq.{lecture['id']}", "kind": "eq.original"}
        )
        if not rows:
            raise ProcessingError("source_missing", "The uploaded file for this lecture is missing. Please add it again.")
        original = rows[0]
        source = ctx.workspace / f"original.{original['storage_path'].rsplit('.', 1)[-1]}"
        limit = settings.max_video_bytes if lecture["source_type"] == "video" else settings.max_audio_bytes
        try:
            await ctx.admin.download_file(BUCKET, original["storage_path"], source, max_bytes=limit)
        except StorageObjectTooLarge:
            raise ProcessingError("file_too_large", "The stored file is larger than the allowed limit.") from None
        return source, original

    provider = provider_named((lecture.get("source_fingerprint") or "").split(":", 1)[0])
    ref = provider.parse(lecture["source_url"])
    if ref is None:
        raise ProcessingError("unsupported_source", "This lecture's source URL is no longer supported.")
    source = await provider.fetch_audio(
        ref, ctx.workspace, max_bytes=settings.max_video_bytes, max_duration_seconds=settings.max_media_duration_seconds
    )
    return source, None


async def prepare_audio(ctx: JobContext) -> AudioArtifact:
    """The lecture's audio as 16 kHz mono FLAC in the job workspace (the input for transcription).

    Later stages call this instead of relying on a previous stage's files: within one run
    it returns the audio already prepared; when a job resumes in a new run (for example a
    job that was waiting for a stage to exist) it rebuilds the audio from the source.
    """
    if ctx.audio is not None and ctx.audio.path.exists():
        return ctx.audio

    settings = ctx.settings
    started = time.monotonic()
    source, original = await _acquire_source(ctx)
    input_bytes = source.stat().st_size
    acquire_ms = int((time.monotonic() - started) * 1000)

    info = await probe(settings.ffprobe_path, source)
    validate_input(info, settings.max_media_duration_seconds)

    started = time.monotonic()
    output = ctx.workspace / NORMALIZED_AUDIO_NAME
    await normalize_audio(settings.ffmpeg_path, source, output, timeout=settings.ffmpeg_timeout_seconds)
    ffmpeg_ms = int((time.monotonic() - started) * 1000)

    result = await probe(settings.ffprobe_path, output)
    if result.sample_rate != TARGET_SAMPLE_RATE or result.channels != TARGET_CHANNELS or not result.duration_seconds:
        raise ProcessingError(
            "audio_extraction_failed", "The extracted audio wasn't in the expected format.", details=result.as_record()
        )
    # The source is no longer needed; free the disk before later stages run.
    if source != output:
        source.unlink(missing_ok=True)

    ctx.audio = AudioArtifact(
        path=output,
        duration_seconds=result.duration_seconds,
        checksum_sha256=await anyio.to_thread.run_sync(_sha256, output),
        probe=result,
        details={
            "input_bytes": input_bytes,
            "input_duration_seconds": info.duration_seconds,
            "input_format": info.format_name,
            "input_has_video": info.has_video,
            "output_bytes": output.stat().st_size,
            "output_duration_seconds": result.duration_seconds,
            "output_format": "flac 16 kHz mono",
            "acquire_ms": acquire_ms,
            "ffmpeg_ms": ffmpeg_ms,
        },
        input_probe=info,
        original_media=original,
    )
    return ctx.audio


async def extract_audio(ctx: JobContext) -> dict:
    """EXTRACTING_AUDIO: validate the source and prepare the normalized audio in the workspace.

    Nothing derived is uploaded. Persisted results are facts only: the lecture's duration,
    the original's probe data, and this stage run's measured details.
    """
    audio = await prepare_audio(ctx)
    await ctx.ensure_active()

    if audio.original_media:
        await ctx.admin.update(
            "lecture_media",
            {"id": f"eq.{audio.original_media['id']}"},
            {"duration_seconds": round(audio.details["input_duration_seconds"], 3), "probe": audio.input_probe.as_record()},
        )
    await ctx.admin.update(
        "lectures", {"id": f"eq.{ctx.lecture['id']}"}, {"duration_seconds": round(audio.details["input_duration_seconds"])}
    )
    return {**audio.details, "output_sha256": audio.checksum_sha256}
