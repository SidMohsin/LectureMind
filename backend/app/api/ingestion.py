import hashlib
import logging
import re
import uuid
from pathlib import Path

import anyio
from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response, status
from pydantic import ValidationError
from starlette.datastructures import UploadFile

from app.api.deps import get_current_user, get_user_db
from app.core.config import Settings, get_settings
from app.core.errors import AppError
from app.core.security import AuthenticatedUser
from app.repositories import lectures as lecture_repo
from app.schemas.ingestion import (
    IngestionLimits,
    IngestionResult,
    JobSummary,
    KindLimits,
    LectureMetadataIn,
    ProcessingDetails,
    SourceSubmission,
)
from app.services.ingestion import JOB_FIELDS, Ingestion, LectureMetadata, StoredUpload
from app.services.queue import JobQueue
from app.services.sources import PROVIDERS, resolve_source
from app.services.supabase_admin import ServiceSupabase
from app.services.supabase_rest import UserScopedSupabase
from app.workers.lifecycle import ProcessingError
from app.workers.media import mime_for, sniff_container
from app.workers.pipeline import implemented_stages

logger = logging.getLogger(__name__)

router = APIRouter(tags=["ingestion"])

MULTIPART_OVERHEAD = 1024 * 1024
FORMATS = {"video": ["MP4", "MOV", "WebM", "MKV"], "audio": ["MP3", "WAV", "M4A", "WebM", "OGG"]}


def get_queue(request: Request) -> JobQueue:
    return request.app.state.queue


def get_ingestion(
    request: Request, settings: Settings = Depends(get_settings), queue: JobQueue = Depends(get_queue)
) -> Ingestion:
    if not settings.ingestion_configured:
        raise AppError(503, "ingestion_unavailable", "Lecture ingestion isn't configured on this server.")
    return Ingestion(ServiceSupabase(request.app.state.http, settings), queue)


def _limit_for(kind: str, settings: Settings) -> int:
    return settings.max_video_bytes if kind == "video" else settings.max_audio_bytes


def _format_bytes(value: int) -> str:
    return f"{value / 1024**3:.1f} GB" if value >= 1024**3 else f"{value / 1024**2:.0f} MB"


def _safe_filename(name: str | None) -> str | None:
    if not name:
        return None
    base = re.split(r"[\\/]", name)[-1]
    base = re.sub(r"[\x00-\x1f\x7f]", "", base).strip()
    return base[:255] or None


def _validation_error(exc: ValidationError) -> AppError:
    first = exc.errors()[0]
    message = str(first.get("msg", "Invalid input.")).removeprefix("Value error, ")
    return AppError(422, "invalid_metadata", message, details=[{"field": e["loc"][-1], "message": e["msg"]} for e in exc.errors()])


def _store_upload(source, directory: Path, max_bytes: int) -> tuple[Path, int, str, bytes]:
    """Copy the uploaded file into private scratch space, hashing it and enforcing the size limit."""
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / f"upload-{uuid.uuid4().hex}.part"
    digest = hashlib.sha256()
    size = 0
    head = b""
    try:
        with target.open("wb") as out:
            while block := source.read(1024 * 1024):
                if not head:
                    head = block[:64]
                size += len(block)
                if size > max_bytes:
                    raise AppError(413, "file_too_large", f"This file is larger than the {_format_bytes(max_bytes)} limit.")
                digest.update(block)
                out.write(block)
    except BaseException:
        target.unlink(missing_ok=True)
        raise
    return target, size, digest.hexdigest(), head


@router.get("/ingestion/limits", response_model=IngestionLimits)
async def ingestion_limits(
    user: AuthenticatedUser = Depends(get_current_user), settings: Settings = Depends(get_settings)
):
    return IngestionLimits(
        video=KindLimits(max_bytes=settings.max_video_bytes, formats=FORMATS["video"]),
        audio=KindLimits(max_bytes=settings.max_audio_bytes, formats=FORMATS["audio"]),
        max_duration_seconds=settings.max_media_duration_seconds,
        source_urls_enabled=settings.source_url_downloads_enabled,
        source_providers=[provider.name for provider in PROVIDERS],
    )


@router.post("/lectures/uploads", response_model=IngestionResult, status_code=status.HTTP_202_ACCEPTED)
async def upload_lecture(
    request: Request,
    response: Response,
    user: AuthenticatedUser = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
    ingestion: Ingestion = Depends(get_ingestion),
    idempotency_key: uuid.UUID | None = Header(default=None, alias="Idempotency-Key"),
):
    # Reject oversized bodies from the declared length, before anything is read.
    declared = request.headers.get("content-length")
    if declared is None or not declared.isdigit():
        raise AppError(411, "length_required", "Upload size must be declared.")
    largest = max(settings.max_video_bytes, settings.max_audio_bytes)
    if int(declared) > largest + MULTIPART_OVERHEAD:
        raise AppError(413, "file_too_large", f"This file is larger than the {_format_bytes(largest)} limit.")

    # Room for every metadata field plus more tags than allowed, so an over-long
    # tag list gets our clear validation message rather than a generic 400.
    form = await request.form(max_files=1, max_fields=60)
    stored_path: Path | None = None
    try:
        kind = form.get("kind")
        if kind not in ("video", "audio"):
            raise AppError(422, "invalid_kind", "Choose whether this is a video or an audio recording.")
        max_bytes = _limit_for(kind, settings)
        if int(declared) > max_bytes + MULTIPART_OVERHEAD:
            raise AppError(413, "file_too_large", f"This file is larger than the {_format_bytes(max_bytes)} limit.")

        upload = form.get("file")
        if not isinstance(upload, UploadFile):
            raise AppError(422, "file_required", "Choose a file to upload.")
        try:
            metadata = LectureMetadataIn(
                title=form.get("title"),
                subject=form.get("subject") or "",
                topic=form.get("topic"),
                instructor=form.get("instructor"),
                lecture_date=form.get("lecture_date") or None,
                tags=[tag for tag in form.getlist("tags") if isinstance(tag, str)],
            )
        except ValidationError as exc:
            raise _validation_error(exc) from None
        if not metadata.title:
            raise AppError(422, "invalid_metadata", "Enter a lecture title.")

        stored_path, size, sha256, head = await anyio.to_thread.run_sync(
            _store_upload, upload.file, settings.work_path / "uploads", max_bytes
        )
        if size == 0:
            raise AppError(422, "empty_file", "This file is empty.")
        container = sniff_container(head)
        mime = mime_for(container, kind) if container else None
        if mime is None:
            raise AppError(
                415,
                "unsupported_media",
                f"This file isn't a supported {kind} format ({', '.join(FORMATS[kind])}).",
            )

        result = await ingestion.create_from_upload(
            user,
            idempotency_key,
            kind,
            LectureMetadata(
                title=metadata.title,
                subject=metadata.subject,
                topic=metadata.topic,
                instructor=metadata.instructor,
                lecture_date=metadata.lecture_date,
                tags=metadata.tags,
            ),
            StoredUpload(
                path=stored_path,
                size=size,
                sha256=sha256,
                mime_type=mime,
                extension=container.extension,
                original_filename=_safe_filename(upload.filename),
            ),
        )
    finally:
        await form.close()
        if stored_path:
            stored_path.unlink(missing_ok=True)

    if result["replayed"]:
        response.status_code = status.HTTP_200_OK
    return result


@router.post("/lectures/sources", response_model=IngestionResult, status_code=status.HTTP_202_ACCEPTED)
async def submit_source(
    body: SourceSubmission,
    request: Request,
    response: Response,
    user: AuthenticatedUser = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
    ingestion: Ingestion = Depends(get_ingestion),
    idempotency_key: uuid.UUID | None = Header(default=None, alias="Idempotency-Key"),
):
    if not settings.source_url_downloads_enabled:
        raise AppError(422, "source_urls_disabled", "Adding lectures from a URL isn't available right now.")
    if not body.rights_confirmed:
        raise AppError(422, "rights_not_confirmed", "Confirm that you have the right to use this video.")
    resolved = resolve_source(str(body.url))
    if resolved is None:
        raise AppError(422, "unsupported_source", "Only links to a single YouTube video are supported.")
    provider, ref = resolved

    if replay := await ingestion.find_replay(user, idempotency_key):
        response.status_code = status.HTTP_200_OK
        return replay
    await ingestion.ensure_not_duplicate(user, ref.fingerprint)

    try:
        info = await provider.check_access(ref, request.app.state.http)
    except ProcessingError as exc:
        raise AppError(503 if exc.retryable else 422, exc.code, exc.message) from None

    title = body.title or (info.title or "").strip()[:300]
    if not title:
        raise AppError(422, "invalid_metadata", "Enter a lecture title.")
    result = await ingestion.create_from_source(
        user,
        idempotency_key,
        LectureMetadata(
            title=title,
            subject=body.subject,
            topic=body.topic,
            instructor=body.instructor or (info.author or None),
            lecture_date=body.lecture_date,
            tags=body.tags,
        ),
        ref.canonical_url,
        ref.fingerprint,
    )
    if result["replayed"]:
        response.status_code = status.HTTP_200_OK
    return result


@router.post("/lectures/{lecture_id}/retry", response_model=JobSummary)
async def retry_processing(
    lecture_id: uuid.UUID,
    user: AuthenticatedUser = Depends(get_current_user),
    ingestion: Ingestion = Depends(get_ingestion),
):
    return await ingestion.retry(user, lecture_id)


@router.get("/lectures/{lecture_id}/processing", response_model=ProcessingDetails)
async def processing_details(
    lecture_id: uuid.UUID,
    user: AuthenticatedUser = Depends(get_current_user),
    db: UserScopedSupabase = Depends(get_user_db),
):
    lecture = await lecture_repo.get_lecture(db, user.id, lecture_id)
    if lecture is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lecture not found.")
    jobs = await db.select("processing_jobs", {"select": JOB_FIELDS, "lecture_id": f"eq.{lecture_id}"})
    job = jobs[0] if jobs else None
    runs = (
        await db.select(
            "processing_stage_runs",
            {
                "select": "stage,attempt,status,started_at,finished_at,duration_ms,error_code",
                "job_id": f"eq.{job['id']}",
                "order": "started_at.asc",
            },
        )
        if job
        else []
    )
    media = await db.select(
        "lecture_media",
        {"select": "kind,mime_type,file_size,duration_seconds,probe", "lecture_id": f"eq.{lecture_id}", "order": "kind.asc"},
    )
    return ProcessingDetails(
        lecture=lecture, job=job, stage_runs=runs, media=media, implemented_stages=implemented_stages()
    )
