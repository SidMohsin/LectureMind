"""The worker + pipeline with real FFmpeg, an in-memory Supabase and an in-memory queue."""

import asyncio
import shutil
import uuid
from datetime import timedelta

import pytest

from app.core.config import Settings
from app.core.errors import UpstreamServiceError
from app.workers import pipeline, stages
from app.workers.context import JobContext
from app.workers.lifecycle import PIPELINE_STAGES, LeaseLost
from app.workers.main import Worker

from .fakes import FakeAdmin, FakeQueue, now
from .media_fixtures import media, requires_ffmpeg  # noqa: F401 - fixture import

pytestmark = [pytest.mark.anyio, requires_ffmpeg]

USER = str(uuid.uuid4())


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
def settings(tmp_path):
    return Settings(
        _env_file=None,
        supabase_url="https://x.supabase.co",
        supabase_anon_key="anon",
        supabase_service_role_key="service",
        work_dir=str(tmp_path / "work"),
        worker_retry_backoff_seconds=30,
        worker_heartbeat_seconds=30,
    )


@pytest.fixture
def admin():
    return FakeAdmin()


@pytest.fixture
def worker(settings, admin):
    return Worker(settings, admin, FakeQueue(), worker_id="worker-a")


async def seed(admin, media, *, name="mp3", source_type="audio", status="QUEUED"):
    lecture = await admin.insert(
        "lectures", {"user_id": USER, "title": "T", "source_type": source_type, "status": status}
    )
    if source_type == "url":
        await admin.update(
            "lectures",
            {"id": f"eq.{lecture['id']}"},
            {"source_url": "https://www.youtube.com/watch?v=ZA-tUyM_y7s", "source_fingerprint": "youtube:ZA-tUyM_y7s"},
        )
    else:
        extension = media[name].suffix.lstrip(".")
        path = f"{USER}/{lecture['id']}/original/source.{extension}"
        admin.storage[f"lectures/{path}"] = media[name].read_bytes()
        await admin.insert(
            "lecture_media",
            {"lecture_id": lecture["id"], "kind": "original", "storage_path": path, "mime_type": "x", "file_size": 1},
        )
    job = await admin.insert("processing_jobs", {"lecture_id": lecture["id"], "user_id": USER})
    return lecture, job


def row(admin, table, id_):
    return admin.rows(table, id=id_)[0]


def workspace_is_empty(settings):
    root = settings.work_path
    return not root.exists() or not any(root.iterdir())


# --- successful extraction ------------------------------------------------------------------


@pytest.mark.parametrize("name,source_type,has_video", [("mp3", "audio", False), ("mp4", "video", True), ("wav", "audio", False)])
async def test_audio_is_extracted_and_job_waits_at_the_phase_boundary(worker, admin, settings, media, name, source_type, has_video):
    lecture, job = await seed(admin, media, name=name, source_type=source_type)

    assert await worker.process(job["id"]) == "waiting"

    stored_lecture = row(admin, "lectures", lecture["id"])
    stored_job = row(admin, "processing_jobs", job["id"])
    assert stored_lecture["status"] == "TRANSCRIBING"  # never READY: nothing has transcribed it
    assert stored_lecture["duration_seconds"] in (2, 3)
    assert stored_job["status"] == "waiting" and stored_job["current_stage"] == "TRANSCRIBING"
    assert stored_job["lease_owner"] is None and "isn't available yet" in stored_job["status_detail"]

    run = admin.rows("processing_stage_runs", job_id=job["id"])[0]
    assert run["stage"] == "EXTRACTING_AUDIO" and run["status"] == "succeeded" and run["duration_ms"] >= 0
    assert run["details"]["input_has_video"] is has_video and run["details"]["output_bytes"] > 0

    assert run["details"]["output_format"] == "flac 16 kHz mono" and len(run["details"]["output_sha256"]) == 64
    # The extracted audio is a temporary artifact: nothing derived is uploaded or recorded as stored media.
    assert admin.rows("lecture_media", lecture_id=lecture["id"], kind="audio") == []
    assert not any(call[0] == "upload" for call in admin.calls)
    assert [key.split("/", 1)[1] for key in admin.storage] == [f"{USER}/{lecture['id']}/original/source.{media[name].suffix.lstrip('.')}"]
    original = admin.rows("lecture_media", lecture_id=lecture["id"], kind="original")[0]
    assert original["duration_seconds"] > 0 and original["probe"]["format"]
    assert workspace_is_empty(settings)


async def test_rerunning_a_stage_leaves_no_extra_persisted_outputs(worker, admin, media):
    lecture, job = await seed(admin, media)
    await worker.process(job["id"])
    # Simulate a crash before the job advanced; the stage runs again from scratch.
    await admin.update("processing_jobs", {"id": f"eq.{job['id']}"}, {"status": "queued", "current_stage": "EXTRACTING_AUDIO"})
    await admin.update("lectures", {"id": f"eq.{lecture['id']}"}, {"status": "EXTRACTING_AUDIO"})

    assert await worker.process(job["id"]) == "waiting"

    assert len(admin.storage) == 1 and len(admin.rows("lecture_media", lecture_id=lecture["id"])) == 1
    assert admin.rows("processing_stage_runs", job_id=job["id"], attempt=2)[0]["details"]["output_bytes"] > 0


async def test_later_stages_get_the_audio_from_the_workspace_and_it_is_deleted_after(worker, admin, settings, media, monkeypatch):
    seen = {}

    async def transcribe(ctx):
        audio = await stages.prepare_audio(ctx)  # what a Phase 5 stage will call
        seen["same_run_path"] = audio.path
        seen["exists"] = audio.path.exists() and audio.path.read_bytes().startswith(b"fLaC")
        seen["inside_workspace"] = ctx.workspace in audio.path.parents
        return {}

    monkeypatch.setitem(pipeline.STAGE_HANDLERS, "TRANSCRIBING", transcribe)
    _, job = await seed(admin, media)
    await worker.process(job["id"])

    assert seen["exists"] and seen["inside_workspace"]
    assert len([call for call in admin.calls if call[0] == "download"]) == 1  # prepared once, reused in the run
    assert not seen["same_run_path"].exists() and workspace_is_empty(settings)


async def test_a_resumed_run_rebuilds_the_audio_locally(worker, admin, media, monkeypatch):
    _, job = await seed(admin, media)
    await worker.process(job["id"])  # waits at TRANSCRIBING; its workspace is already gone

    seen = {}

    async def transcribe(ctx):
        audio = await stages.prepare_audio(ctx)
        seen["rebuilt"] = audio.path.exists() and audio.path.read_bytes().startswith(b"fLaC")
        return {}

    monkeypatch.setitem(pipeline.STAGE_HANDLERS, "TRANSCRIBING", transcribe)
    assert job["id"] in await worker.recover()
    await worker.process(job["id"])

    assert seen["rebuilt"]
    assert not any(call[0] == "upload" for call in admin.calls)


# --- failures ------------------------------------------------------------------------------------


@pytest.mark.parametrize("name,code", [("corrupt", "media_unreadable"), ("video_only", "no_audio_stream")])
async def test_bad_media_fails_permanently_with_reason(worker, admin, settings, media, name, code):
    lecture, job = await seed(admin, media, name=name, source_type="video")

    assert await worker.process(job["id"]) == "failed"

    stored_job = row(admin, "processing_jobs", job["id"])
    assert stored_job["status"] == "failed" and stored_job["error_code"] == code
    assert stored_job["retryable"] is False and stored_job["error_message"] and stored_job["failed_at"]
    assert row(admin, "lectures", lecture["id"])["status"] == "FAILED"
    run = admin.rows("processing_stage_runs", job_id=job["id"])[0]
    assert run["status"] == "failed" and run["error_code"] == code
    assert not any(key.endswith("audio.flac") for key in admin.storage)
    assert workspace_is_empty(settings)


async def test_overlong_media_is_rejected(admin, settings, media):
    worker = Worker(settings.model_copy(update={"max_media_duration_seconds": 1}), admin, FakeQueue(), worker_id="w")
    _, job = await seed(admin, media)
    assert await worker.process(job["id"]) == "failed"
    assert row(admin, "processing_jobs", job["id"])["error_code"] == "media_too_long"


async def test_transient_failure_is_retried_with_backoff_then_succeeds(worker, admin, media):
    lecture, job = await seed(admin, media)
    admin.fail_download = UpstreamServiceError()

    assert await worker.process(job["id"]) == "queued"
    stored = row(admin, "processing_jobs", job["id"])
    assert stored["retryable"] is True and stored["error_code"] == "service_unavailable"
    assert stored["next_attempt_at"] > now().isoformat()
    assert row(admin, "lectures", lecture["id"])["status"] == "QUEUED"
    assert await worker.process(job["id"]) is None  # backoff not elapsed: not claimable yet

    admin.fail_download = None
    await admin.update("processing_jobs", {"id": f"eq.{job['id']}"}, {"next_attempt_at": (now() - timedelta(seconds=1)).isoformat()})
    assert await worker.process(job["id"]) == "waiting"
    assert row(admin, "processing_jobs", job["id"])["error_code"] is None


async def test_transient_failures_stop_after_max_attempts(worker, admin, media):
    _, job = await seed(admin, media)
    admin.fail_download = UpstreamServiceError()
    outcomes = []
    for _ in range(3):
        await admin.update("processing_jobs", {"id": f"eq.{job['id']}"}, {"next_attempt_at": now().isoformat()})
        outcomes.append(await worker.process(job["id"]))
    assert outcomes == ["queued", "queued", "failed"]
    stored = row(admin, "processing_jobs", job["id"])
    assert stored["attempt_count"] == 3 and stored["retryable"] is True  # the user may retry manually


async def test_unexpected_exception_is_recorded_as_retryable(worker, admin, media, monkeypatch):
    async def broken(ctx):
        raise KeyError("bug")

    monkeypatch.setitem(pipeline.STAGE_HANDLERS, "EXTRACTING_AUDIO", broken)
    _, job = await seed(admin, media)
    assert await worker.process(job["id"]) == "queued"
    assert row(admin, "processing_jobs", job["id"])["error_code"] == "internal_error"


# --- duplicates, crashes, leases ----------------------------------------------------------------


async def test_duplicate_notifications_run_the_job_once(worker, admin, media):
    _, job = await seed(admin, media)
    other = Worker(worker.settings, admin, FakeQueue(), worker_id="worker-b")
    outcomes = await asyncio.gather(worker.process(job["id"]), other.process(job["id"]))
    assert sorted(outcomes, key=str) == sorted(["waiting", None], key=str)
    assert len(admin.rows("processing_stage_runs", job_id=job["id"])) == 1
    assert await worker.process(job["id"]) is None  # a late duplicate is ignored


async def test_job_abandoned_by_a_crashed_worker_is_recovered(worker, admin, media):
    _, job = await seed(admin, media)
    claimed = await admin.rpc("claim_processing_job", {"p_job_id": job["id"], "p_worker": "crashed", "p_lease_seconds": 60})
    assert claimed
    await admin.update(
        "processing_jobs", {"id": f"eq.{job['id']}"}, {"lease_expires_at": (now() - timedelta(seconds=1)).isoformat()}
    )

    assert job["id"] in await worker.recover()
    assert await worker.process(job["id"]) == "waiting"
    assert row(admin, "processing_jobs", job["id"])["attempt_count"] == 2


async def test_stale_worker_cannot_overwrite_state(admin, settings, media, tmp_path):
    lecture, job = await seed(admin, media)
    await admin.rpc("claim_processing_job", {"p_job_id": job["id"], "p_worker": "new-owner", "p_lease_seconds": 60})
    ctx = JobContext(admin, settings, "old-owner", row(admin, "processing_jobs", job["id"]), lecture, tmp_path)
    with pytest.raises(LeaseLost):
        await pipeline._update_job(ctx, {"status": "failed"})
    assert row(admin, "processing_jobs", job["id"])["status"] == "running"


async def test_lost_lease_stops_the_run(admin, settings, media, monkeypatch):
    async def slow(ctx):
        await asyncio.sleep(5)
        return {}

    monkeypatch.setitem(pipeline.STAGE_HANDLERS, "EXTRACTING_AUDIO", slow)
    fast = Worker(settings.model_copy(update={"worker_heartbeat_seconds": 0.05}), admin, FakeQueue(), worker_id="w")
    _, job = await seed(admin, media)
    admin.lease_valid = False  # e.g. lecture deleted or another worker recovered it
    assert await asyncio.wait_for(fast.process(job["id"]), timeout=3) is None
    assert workspace_is_empty(settings)


async def test_lecture_deleted_during_extraction_persists_nothing(worker, admin, settings, media, monkeypatch):
    lecture, job = await seed(admin, media)
    real_rpc = admin.rpc
    renewals = {"count": 0}

    async def rpc(function, args):
        if function == "renew_processing_lease":
            renewals["count"] += 1
            return False  # the lecture was deleted / the job taken over while FFmpeg ran
        return await real_rpc(function, args)

    monkeypatch.setattr(admin, "rpc", rpc)
    assert await worker.process(job["id"]) is None
    assert not any(call[0] == "upload" for call in admin.calls) and not any(key.endswith("audio.flac") for key in admin.storage)
    assert workspace_is_empty(settings)


async def test_deleted_lecture_is_skipped(worker, admin, media):
    lecture, job = await seed(admin, media)
    await admin.delete("lectures", {"id": f"eq.{lecture['id']}"})
    assert await worker.process(job["id"]) is None


# --- queue integration -------------------------------------------------------------------------


async def test_worker_consumes_jobs_from_the_queue(settings, admin, media):
    queue = FakeQueue()
    worker = Worker(settings, admin, queue, worker_id="w")
    _, job = await seed(admin, media)
    await queue.enqueue(job["id"])
    stop = asyncio.Event()
    task = asyncio.create_task(worker.run(stop))
    for _ in range(300):
        if row(admin, "processing_jobs", job["id"])["status"] == "waiting":
            break
        await asyncio.sleep(0.05)
    stop.set()
    await asyncio.wait_for(task, timeout=5)
    assert row(admin, "processing_jobs", job["id"])["status"] == "waiting"


async def test_jobs_still_run_when_redis_is_down(settings, admin, media):
    worker = Worker(settings, admin, FakeQueue(fail=True), worker_id="w")
    _, job = await seed(admin, media)
    await worker._sweep()
    assert row(admin, "processing_jobs", job["id"])["status"] == "waiting"


# --- source URLs + the Phase 5 plug-in path -------------------------------------------------------


async def test_source_url_lecture_goes_through_the_same_pipeline(worker, admin, media, monkeypatch):
    class FakeProvider:
        name = "youtube"

        def parse(self, url):
            from app.services.sources import YouTubeProvider

            return YouTubeProvider().parse(url)

        async def fetch_audio(self, ref, directory, *, max_bytes, max_duration_seconds):
            target = directory / "source.webm"
            shutil.copy(media["mp3"], target)
            return target

    monkeypatch.setattr(stages, "provider_named", lambda name: FakeProvider())
    lecture, job = await seed(admin, media, source_type="url")
    assert await worker.process(job["id"]) == "waiting"
    assert admin.rows("processing_stage_runs", job_id=job["id"])[0]["details"]["input_format"]


async def test_waiting_job_resumes_when_its_stage_is_implemented(worker, admin, media, monkeypatch):
    lecture, job = await seed(admin, media)
    await worker.process(job["id"])
    assert row(admin, "processing_jobs", job["id"])["status"] == "waiting"

    async def transcribe(ctx):
        return {"segments": 0}

    monkeypatch.setitem(pipeline.STAGE_HANDLERS, "TRANSCRIBING", transcribe)
    assert job["id"] in await worker.recover()
    assert await worker.process(job["id"]) == "waiting"
    stored = row(admin, "processing_jobs", job["id"])
    assert stored["current_stage"] == "CLEANING"
    assert row(admin, "lectures", lecture["id"])["status"] == "CLEANING"


async def test_lecture_becomes_ready_only_when_every_stage_has_run(worker, admin, media, monkeypatch):
    async def done(ctx):
        return {}

    for stage in PIPELINE_STAGES:
        monkeypatch.setitem(pipeline.STAGE_HANDLERS, stage, done)
    lecture, job = await seed(admin, media)
    assert await worker.process(job["id"]) == "succeeded"
    assert row(admin, "lectures", lecture["id"])["status"] == "READY"
    assert [r["stage"] for r in admin.rows("processing_stage_runs", job_id=job["id"])] == list(PIPELINE_STAGES)
