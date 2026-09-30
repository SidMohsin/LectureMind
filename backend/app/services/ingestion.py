"""Lecture ingestion: turn a validated upload or source URL into a lecture + processing job.

Both input types converge here: create lecture -> (store original) -> create
the lecture's single processing job -> notify the queue. Heavy work (download,
ffprobe, FFmpeg) happens later in the worker.

Duplicate protection:
  * client_request_id (Idempotency-Key): replaying the same submission returns
    the lecture it already created instead of creating another.
  * source_fingerprint (sha256 of the file / provider video id): the same
    content can't be added twice to one user's library.
Both are backed by unique indexes, so concurrent requests are safe too.
"""

import logging
import uuid
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path

from app.core.errors import AppError
from app.core.security import AuthenticatedUser
from app.services.queue import JobQueue
from app.services.supabase_admin import ConflictError, ServiceSupabase, StorageObjectTooLarge

logger = logging.getLogger(__name__)

BUCKET = "lectures"
LECTURE_FIELDS = (
    "id,title,subject,topic,instructor,lecture_date,tags,source_type,source_url,status,"
    "duration_seconds,original_filename,created_at,updated_at"
)
JOB_FIELDS = (
    "id,status,current_stage,attempt_count,max_attempts,error_code,error_message,retryable,status_detail,"
    "queued_at,started_at,finished_at,failed_at,next_attempt_at,updated_at"
)


@dataclass(frozen=True)
class LectureMetadata:
    title: str
    subject: str
    topic: str | None
    instructor: str | None
    lecture_date: date | None
    tags: list[str]


@dataclass(frozen=True)
class StoredUpload:
    path: Path
    size: int
    sha256: str
    mime_type: str
    extension: str
    original_filename: str | None


def original_object_path(user_id: uuid.UUID, lecture_id: str, extension: str) -> str:
    # Server-chosen name: the user's filename never becomes part of a storage path.
    return f"{user_id}/{lecture_id}/original/source.{extension}"


class Ingestion:
    def __init__(self, admin: ServiceSupabase, queue: JobQueue):
        self.admin = admin
        self.queue = queue

    # --- idempotency / duplicates --------------------------------------------------------

    async def _lecture_by(self, user_id: uuid.UUID, column: str, value: str) -> dict | None:
        rows = await self.admin.select(
            "lectures", {"select": LECTURE_FIELDS, "user_id": f"eq.{user_id}", column: f"eq.{value}"}
        )
        return rows[0] if rows else None

    async def _job_for(self, lecture_id: str) -> dict | None:
        rows = await self.admin.select("processing_jobs", {"select": JOB_FIELDS, "lecture_id": f"eq.{lecture_id}"})
        return rows[0] if rows else None

    async def find_replay(self, user: AuthenticatedUser, request_id: uuid.UUID | None) -> dict | None:
        if request_id is None:
            return None
        lecture = await self._lecture_by(user.id, "client_request_id", str(request_id))
        if lecture is None:
            return None
        return {"lecture": lecture, "job": await self._job_for(lecture["id"]), "replayed": True}

    async def ensure_not_duplicate(self, user: AuthenticatedUser, fingerprint: str) -> None:
        existing = await self._lecture_by(user.id, "source_fingerprint", fingerprint)
        if existing:
            raise AppError(
                409,
                "duplicate_lecture",
                "This lecture is already in your library.",
                details={"lecture_id": existing["id"], "title": existing["title"]},
            )

    # --- creation ------------------------------------------------------------------------

    async def _insert_lecture(self, user: AuthenticatedUser, request_id: uuid.UUID | None, row: dict) -> dict:
        try:
            return await self.admin.insert(
                "lectures",
                {**row, "user_id": str(user.id), "client_request_id": str(request_id) if request_id else None},
            )
        except ConflictError:
            # A concurrent identical submission won the race.
            replay = await self.find_replay(user, request_id)
            if replay:
                raise _Replay(replay) from None
            await self.ensure_not_duplicate(user, row["source_fingerprint"])
            raise

    async def _start_processing(self, lecture: dict, user: AuthenticatedUser) -> dict:
        job = await self.admin.insert("processing_jobs", {"lecture_id": lecture["id"], "user_id": str(user.id)})
        updated = await self.admin.update(
            "lectures", {"id": f"eq.{lecture['id']}", "status": "eq.UPLOADED"}, {"status": "QUEUED"}
        )
        lecture.update(updated[0] if updated else {"status": "QUEUED"})
        await self.notify(job["id"])
        return {key: job.get(key) for key in JOB_FIELDS.split(",")}

    async def notify(self, job_id: str) -> None:
        """Best effort: if Redis is unavailable the job stays queued and the worker's sweep finds it."""
        try:
            await self.queue.enqueue(job_id)
        except Exception as exc:  # noqa: BLE001 - any queue failure is recoverable
            logger.warning("Could not notify queue for job %s (%s); the recovery sweep will pick it up.", job_id, exc)

    async def create_from_upload(
        self, user: AuthenticatedUser, request_id: uuid.UUID | None, kind: str, metadata: LectureMetadata, upload: StoredUpload
    ) -> dict:
        if replay := await self.find_replay(user, request_id):
            return replay
        fingerprint = f"sha256:{upload.sha256}"
        await self.ensure_not_duplicate(user, fingerprint)

        try:
            lecture = await self._insert_lecture(
                user,
                request_id,
                {
                    **_metadata_row(metadata),
                    "source_type": kind,
                    "original_filename": upload.original_filename,
                    "source_fingerprint": fingerprint,
                },
            )
        except _Replay as replay:
            return replay.result

        object_path = original_object_path(user.id, lecture["id"], upload.extension)
        stored = False
        try:
            await self.admin.upload_file(BUCKET, object_path, upload.path, upload.mime_type, upsert=False)
            stored = True
            await self.admin.insert(
                "lecture_media",
                {
                    "lecture_id": lecture["id"],
                    "kind": "original",
                    "storage_path": object_path,
                    "mime_type": upload.mime_type,
                    "file_size": upload.size,
                    "checksum_sha256": upload.sha256,
                },
            )
            job = await self._start_processing(lecture, user)
        except BaseException as exc:
            await self._discard(lecture["id"], object_path if stored else None)
            if isinstance(exc, StorageObjectTooLarge):
                raise AppError(413, "file_too_large", "This file is larger than your storage plan allows.") from None
            raise
        return {"lecture": lecture, "job": job, "replayed": False}

    async def create_from_source(
        self,
        user: AuthenticatedUser,
        request_id: uuid.UUID | None,
        metadata: LectureMetadata,
        canonical_url: str,
        fingerprint: str,
    ) -> dict:
        try:
            lecture = await self._insert_lecture(
                user,
                request_id,
                {
                    **_metadata_row(metadata),
                    "source_type": "url",
                    "source_url": canonical_url,
                    "source_fingerprint": fingerprint,
                    "source_rights_confirmed_at": datetime.now(timezone.utc).isoformat(),
                },
            )
        except _Replay as replay:
            return replay.result
        try:
            job = await self._start_processing(lecture, user)
        except BaseException:
            await self._discard(lecture["id"], None)
            raise
        return {"lecture": lecture, "job": job, "replayed": False}

    async def _discard(self, lecture_id: str, object_path: str | None) -> None:
        """Undo a partially created lecture so a failed submission leaves nothing behind."""
        try:
            if object_path:
                await self.admin.remove_objects(BUCKET, [object_path])
            await self.admin.delete("lectures", {"id": f"eq.{lecture_id}"})
        except Exception:  # noqa: BLE001
            logger.exception("Could not clean up partially created lecture %s", lecture_id)

    # --- retry ---------------------------------------------------------------------------

    async def retry(self, user: AuthenticatedUser, lecture_id: uuid.UUID) -> dict:
        job = await self._job_for(str(lecture_id))
        if job is None or not await self._lecture_by(user.id, "id", str(lecture_id)):
            raise AppError(404, "not_found", "Lecture not found.")
        if job["status"] != "failed":
            raise AppError(409, "not_retryable", "This lecture isn't in a failed state.")
        if not job["retryable"]:
            raise AppError(
                409, "not_retryable", "Retrying won't help with this problem. Delete the lecture and add it again."
            )
        updated = await self.admin.update(
            "processing_jobs",
            {"id": f"eq.{job['id']}", "status": "eq.failed"},
            {
                "status": "queued",
                "next_attempt_at": datetime.now(timezone.utc).isoformat(),
                # A manual retry gets a fresh automatic-retry budget.
                "max_attempts": job["attempt_count"] + 3,
                "error_code": None,
                "error_message": None,
                "retryable": None,
                "failed_at": None,
                "finished_at": None,
                "status_detail": "Retry requested.",
                "queued_at": datetime.now(timezone.utc).isoformat(),
            },
        )
        if not updated:
            raise AppError(409, "not_retryable", "This lecture is already being retried.")
        await self.admin.update("lectures", {"id": f"eq.{lecture_id}", "status": "eq.FAILED"}, {"status": "QUEUED"})
        await self.notify(job["id"])
        return {key: updated[0].get(key) for key in JOB_FIELDS.split(",")}


class _Replay(Exception):
    def __init__(self, result: dict):
        self.result = result


def _metadata_row(metadata: LectureMetadata) -> dict:
    return {
        "title": metadata.title,
        "subject": metadata.subject,
        "topic": metadata.topic,
        "instructor": metadata.instructor,
        "lecture_date": metadata.lecture_date.isoformat() if metadata.lecture_date else None,
        "tags": metadata.tags,
    }
