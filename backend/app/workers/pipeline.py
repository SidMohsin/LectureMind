"""Runs a claimed job through the lifecycle, one stage at a time.

Every write to the job is conditional on this worker still holding the lease,
and lecture status changes are compare-and-set, so a worker that lost its job
(crash recovery, duplicate delivery) can never overwrite newer state.
"""

import logging
import time
from datetime import datetime, timedelta, timezone
from typing import Awaitable, Callable

from app.core.errors import UpstreamServiceError
from app.workers.context import JobContext
from app.workers.lifecycle import (
    LeaseLost,
    ProcessingError,
    next_stage,
    require_lecture_transition,
)
from app.workers import intelligence_stages
from app.workers.stages import extract_audio

logger = logging.getLogger(__name__)

StageHandler = Callable[[JobContext], Awaitable[dict]]

STAGE_HANDLERS: dict[str, StageHandler] = {
    "EXTRACTING_AUDIO": extract_audio,
    "TRANSCRIBING": intelligence_stages.transcribe,
    "CLEANING": intelligence_stages.clean,
    "CHUNKING": intelligence_stages.chunk,
    "EMBEDDING": intelligence_stages.embed,
    "INDEXING": intelligence_stages.index,
    "GENERATING_INTELLIGENCE": intelligence_stages.generate_intelligence,
}

STAGE_LABELS = {
    "EXTRACTING_AUDIO": "Audio extraction",
    "TRANSCRIBING": "Transcription",
    "CLEANING": "Transcript cleaning",
    "CHUNKING": "Semantic chunking",
    "EMBEDDING": "Embedding",
    "INDEXING": "Indexing",
    "GENERATING_INTELLIGENCE": "Lecture intelligence",
}


def implemented_stages() -> list[str]:
    return list(STAGE_HANDLERS)


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def _update_job(ctx: JobContext, values: dict) -> None:
    rows = await ctx.admin.update(
        "processing_jobs",
        {"id": f"eq.{ctx.job_id}", "status": "eq.running", "lease_owner": f"eq.{ctx.worker_id}"},
        values,
    )
    if not rows:
        raise LeaseLost()
    ctx.job.update(rows[0])


async def _set_lecture_status(ctx: JobContext, target: str) -> None:
    current = ctx.lecture["status"]
    if current == target:
        return  # e.g. resuming a stage after a lost worker
    require_lecture_transition(current, target)
    rows = await ctx.admin.update(
        "lectures", {"id": f"eq.{ctx.lecture['id']}", "status": f"eq.{current}"}, {"status": target}
    )
    if not rows:
        raise LeaseLost()  # lecture deleted or changed underneath us
    ctx.lecture["status"] = target


async def _start_run(ctx: JobContext, stage: str) -> str:
    run = await ctx.admin.insert(
        "processing_stage_runs", {"job_id": ctx.job_id, "stage": stage, "attempt": ctx.job["attempt_count"]}
    )
    return run["id"]


async def _finish_run(
    ctx: JobContext, run_id: str, started: float, *, stage: str, error: ProcessingError | None, details: dict
) -> None:
    duration_ms = int((time.monotonic() - started) * 1000)
    logger.info(
        "stage_finished job_id=%s lecture_id=%s stage=%s attempt=%s outcome=%s duration_ms=%s error_code=%s",
        ctx.job_id, ctx.lecture["id"], stage, ctx.job["attempt_count"],
        "failed" if error else "succeeded", duration_ms, error.code if error else "-",
    )
    await ctx.admin.update(
        "processing_stage_runs",
        {"id": f"eq.{run_id}"},
        {
            "status": "failed" if error else "succeeded",
            "finished_at": _now().isoformat(),
            "duration_ms": duration_ms,
            "error_code": error.code if error else None,
            "details": {**details, **({"error": error.details} if error and error.details else {})},
        },
    )


async def _fail(ctx: JobContext, error: ProcessingError) -> str:
    job = ctx.job
    attempts, limit = job["attempt_count"], job["max_attempts"]
    if error.retryable and attempts < limit:
        delay = ctx.settings.worker_retry_backoff_seconds * 2 ** (attempts - 1)
        await _set_lecture_status(ctx, "QUEUED")
        await _update_job(
            ctx,
            {
                "status": "queued",
                "next_attempt_at": (_now() + timedelta(seconds=delay)).isoformat(),
                "lease_owner": None,
                "lease_expires_at": None,
                "error_code": error.code,
                "error_message": error.message,
                "retryable": True,
                "status_detail": f"A temporary problem occurred. Retrying automatically (attempt {attempts + 1} of {limit}).",
            },
        )
        return "queued"

    await _set_lecture_status(ctx, "FAILED")
    now = _now().isoformat()
    await _update_job(
        ctx,
        {
            "status": "failed",
            "failed_at": now,
            "finished_at": now,
            "lease_owner": None,
            "lease_expires_at": None,
            "error_code": error.code,
            "error_message": error.message,
            "retryable": error.retryable,
            "status_detail": None,
        },
    )
    return "failed"


def _as_processing_error(exc: Exception) -> ProcessingError:
    if isinstance(exc, ProcessingError):
        return exc
    if isinstance(exc, UpstreamServiceError):
        return ProcessingError(
            "service_unavailable", "A storage or database service was temporarily unavailable.", retryable=True
        )
    return ProcessingError(
        "internal_error",
        "Something went wrong while processing this lecture.",
        retryable=True,
        details={"exception": repr(exc)[:500]},
    )


async def run_job(ctx: JobContext) -> str:
    """Advance the job from its current stage. Returns the resulting job status."""
    stage = ctx.job["current_stage"]
    while True:
        handler = STAGE_HANDLERS.get(stage)
        if handler is None:
            # Honest phase boundary: nothing can perform this stage yet.
            await _set_lecture_status(ctx, stage)
            await _update_job(
                ctx,
                {
                    "status": "waiting",
                    "lease_owner": None,
                    "lease_expires_at": None,
                    "status_detail": f"{STAGE_LABELS[stage]} isn't available yet. Processing will continue from here once it is.",
                },
            )
            return "waiting"

        await _set_lecture_status(ctx, stage)
        run_id = await _start_run(ctx, stage)
        started = time.monotonic()
        try:
            details = await handler(ctx)
        except LeaseLost:
            raise
        except Exception as exc:  # noqa: BLE001 - every failure is recorded on the job
            error = _as_processing_error(exc)
            if error.code == "internal_error":
                logger.exception("Stage %s crashed for job %s", stage, ctx.job_id)
            await _finish_run(ctx, run_id, started, stage=stage, error=error, details={})
            return await _fail(ctx, error)

        await _finish_run(ctx, run_id, started, stage=stage, error=None, details=details)
        following = next_stage(stage)
        if following is None:
            await _set_lecture_status(ctx, "READY")
            now = _now().isoformat()
            await _update_job(
                ctx,
                {"status": "succeeded", "finished_at": now, "lease_owner": None, "lease_expires_at": None, "status_detail": None},
            )
            return "succeeded"
        await _update_job(ctx, {"current_stage": following, "error_code": None, "error_message": None, "retryable": None})
        stage = following
