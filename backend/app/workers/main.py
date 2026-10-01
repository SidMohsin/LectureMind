"""LectureMind processing worker.

Run with:  python -m app.workers.main

Loop: wait on the Redis queue for job ids; claim each job in Postgres with a
lease (so only one worker ever runs it); keep the lease alive with a heartbeat
while the pipeline runs. A periodic database sweep re-queues jobs whose worker
died, jobs whose retry delay has passed, and notifications Redis lost. If Redis
is unreachable, due jobs from the sweep are processed directly.
"""

import asyncio
import contextlib
import logging
import os
import socket
import time
import uuid
from datetime import datetime, timedelta, timezone

import httpx

from app.core.config import Settings, get_settings
from app.core.logging import configure_logging
from app.core.observability import correlation_id
from app.services.queue import JobQueue, RedisJobQueue
from app.services.supabase_admin import ServiceSupabase
from app.workers.context import JobContext
from app.workers.lifecycle import LeaseLost
from app.workers.pipeline import implemented_stages, run_job
from app.workers.workspace import job_workspace, remove_stale_workspaces

logger = logging.getLogger("app.workers")


class Worker:
    def __init__(self, settings: Settings, admin: ServiceSupabase, queue: JobQueue, worker_id: str | None = None):
        self.settings = settings
        self.admin = admin
        self.queue = queue
        self.worker_id = worker_id or f"{socket.gethostname()}-{os.getpid()}-{uuid.uuid4().hex[:6]}"
        self.started_at = datetime.now(timezone.utc).isoformat()
        self.current_job: str | None = None

    # --- recovery ------------------------------------------------------------------------

    async def recover(self) -> list[str]:
        """Resume waiting jobs whose stage now exists, recover abandoned jobs, return due job ids."""
        implemented = implemented_stages()
        waiting = await self.admin.select(
            "processing_jobs",
            {"select": "id", "status": "eq.waiting", "current_stage": f"in.({','.join(implemented)})"},
        )
        for row in waiting:
            await self.admin.update(
                "processing_jobs",
                {"id": f"eq.{row['id']}", "status": "eq.waiting"},
                {
                    "status": "queued",
                    "status_detail": "Resuming processing.",
                    "next_attempt_at": datetime.now(timezone.utc).isoformat(),
                },
            )
        due = await self.admin.rpc("recover_processing_jobs", {"p_limit": 50})
        return [row["job_id"] for row in due]

    # --- one job -------------------------------------------------------------------------

    async def process(self, job_id: str) -> str | None:
        claimed = await self.admin.rpc(
            "claim_processing_job",
            {"p_job_id": job_id, "p_worker": self.worker_id, "p_lease_seconds": self.settings.worker_lease_seconds},
        )
        if not claimed:
            return None  # already taken, not due, or no longer queued: stale notification
        job = claimed[0]
        lectures = await self.admin.select(
            "lectures",
            {"select": "id,user_id,status,source_type,source_url,source_fingerprint", "id": f"eq.{job['lecture_id']}"},
        )
        if not lectures:
            return None  # deleted in the meantime; the job row cascaded with it

        correlation = correlation_id.set(job_id)  # every log line of this run carries the job id
        self.current_job = job_id
        try:
            logger.info("Job %s: running stage %s (attempt %s)", job_id, job["current_stage"], job["attempt_count"])
            with job_workspace(self.settings.work_path, job_id) as workspace:
                ctx = JobContext(self.admin, self.settings, self.worker_id, job, lectures[0], workspace)
                work = asyncio.create_task(run_job(ctx))
                heartbeat = asyncio.create_task(self._heartbeat(ctx, work))
                try:
                    outcome = await work
                except (LeaseLost, asyncio.CancelledError):
                    logger.warning("Job %s: lease lost; stopping without further writes.", job_id)
                    outcome = None
                finally:
                    heartbeat.cancel()
                    with contextlib.suppress(asyncio.CancelledError):
                        await heartbeat
            logger.info("Job %s: %s", job_id, outcome)
            return outcome
        finally:
            self.current_job = None
            correlation_id.reset(correlation)

    async def _heartbeat(self, ctx: JobContext, work: asyncio.Task) -> None:
        while True:
            await asyncio.sleep(self.settings.worker_heartbeat_seconds)
            try:
                await ctx.ensure_active()
            except LeaseLost:
                work.cancel()
                return
            except Exception:  # noqa: BLE001 - a transient failure; the lease has slack
                logger.warning("Job %s: heartbeat failed; will retry.", ctx.job_id)

    # --- main loop -----------------------------------------------------------------------

    async def run(self, stop: asyncio.Event) -> None:
        stale_after = max(3600, self.settings.worker_lease_seconds * 4)
        remove_stale_workspaces(self.settings.work_path, older_than_seconds=stale_after)
        logger.info("Worker %s started (stages: %s)", self.worker_id, ", ".join(implemented_stages()))
        next_sweep = 0.0
        next_cleanup = time.monotonic() + stale_after
        while not stop.is_set():
            if time.monotonic() >= next_sweep:
                next_sweep = time.monotonic() + self.settings.worker_recovery_interval_seconds
                await self._sweep()
            if time.monotonic() >= next_cleanup:
                # Long-running workers also clear workspaces left behind by crashed workers.
                next_cleanup = time.monotonic() + stale_after
                remove_stale_workspaces(self.settings.work_path, older_than_seconds=stale_after)
            try:
                job_id = await self.queue.dequeue(timeout_seconds=min(5, self.settings.worker_recovery_interval_seconds))
            except Exception as exc:  # noqa: BLE001
                logger.warning("Queue unavailable (%s); relying on the database sweep.", exc)
                await asyncio.sleep(2)
                continue
            if job_id:
                await self._safe_process(job_id)

    async def announce(self) -> None:
        """Refresh this worker's presence for readiness checks (best effort)."""
        try:
            await self.queue.announce_worker(
                self.worker_id,
                {
                    "worker_id": self.worker_id,
                    "started_at": self.started_at,
                    "last_seen": datetime.now(timezone.utc).isoformat(),
                    "busy": self.current_job is not None,
                },
                self.settings.worker_presence_ttl_seconds,
            )
        except Exception as exc:  # noqa: BLE001 - presence is informational
            logger.warning("worker_presence_failed error=%s", type(exc).__name__)

    async def find_stuck_jobs(self) -> dict:
        """Jobs that look stuck: due but not picked up for too long, or running far beyond normal.

        Only reported (logged). The sweep itself re-queues jobs whose worker died, and fails
        those that have already used every attempt (recover_processing_jobs).
        """
        now = datetime.now(timezone.utc)
        queued_cutoff = (now - timedelta(seconds=self.settings.stuck_queued_seconds)).isoformat()
        running_cutoff = (now - timedelta(seconds=self.settings.stuck_running_seconds)).isoformat()
        overdue = await self.admin.select(
            "processing_jobs",
            {"select": "id,lecture_id,current_stage", "status": "eq.queued", "next_attempt_at": f"lt.{queued_cutoff}"},
        )
        long_running = await self.admin.select(
            "processing_jobs",
            {"select": "id,lecture_id,current_stage", "status": "eq.running", "started_at": f"lt.{running_cutoff}"},
        )
        for kind, jobs in (("queued_overdue", overdue), ("long_running", long_running)):
            for job in jobs:
                logger.warning(
                    "stuck_job kind=%s job_id=%s lecture_id=%s stage=%s", kind, job["id"], job["lecture_id"], job["current_stage"]
                )
        return {"queued_overdue": [job["id"] for job in overdue], "long_running": [job["id"] for job in long_running]}

    async def _sweep(self) -> None:
        await self.announce()
        try:
            await self.find_stuck_jobs()
        except Exception:  # noqa: BLE001 - detection must never stop processing
            logger.warning("stuck_job_check_failed")
        try:
            due = await self.recover()
        except Exception:  # noqa: BLE001
            logger.exception("Recovery sweep failed")
            return
        for job_id in due:
            try:
                await self.queue.enqueue(job_id, dedupe_seconds=self.settings.worker_recovery_interval_seconds * 2)
            except Exception:  # noqa: BLE001 - Redis down: don't let jobs stall
                await self._safe_process(job_id)

    async def _safe_process(self, job_id: str) -> None:
        try:
            await self.process(job_id)
        except Exception:  # noqa: BLE001 - the job's lease expires and the sweep retries it
            logger.exception("Job %s: unexpected worker error", job_id)


async def main() -> None:
    configure_logging()
    settings = get_settings()
    if not settings.ingestion_configured:
        raise SystemExit("SUPABASE_URL, SUPABASE_ANON_KEY and SUPABASE_SERVICE_ROLE_KEY must be set for the worker.")
    stop = asyncio.Event()
    queue = RedisJobQueue(settings.redis_url, settings.queue_name)
    async with httpx.AsyncClient(timeout=30.0) as http:
        worker = Worker(settings, ServiceSupabase(http, settings), queue)
        try:
            await worker.run(stop)
        finally:
            await queue.close()


if __name__ == "__main__":
    with contextlib.suppress(KeyboardInterrupt):
        asyncio.run(main())
