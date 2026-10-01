"""Phase 4 against the real Supabase project: schema/RLS, worker RPCs, and a genuine
upload -> job -> worker -> FFmpeg -> storage run (queue replaced by an in-memory list)."""

import subprocess
import uuid
from datetime import datetime, timedelta, timezone

import httpx
import pytest

from app.api import ingestion as ingestion_api
from app.core.config import Settings, get_settings
from app.main import app
from app.services.supabase_admin import ServiceSupabase
from app.workers.main import Worker

from ..fakes import FakeQueue, ffmpeg_available
from .conftest import _env, integration

pytestmark = [pytest.mark.anyio, *integration, pytest.mark.skipif(not ffmpeg_available(), reason="ffmpeg not installed")]

BUCKET = "lectures"


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture(autouse=True)
def audio_stage_only(monkeypatch):
    """Phase 4 scope: stop after audio extraction (Phase 5 stages have their own live test)."""
    from app.workers import pipeline

    monkeypatch.setattr(pipeline, "STAGE_HANDLERS", {"EXTRACTING_AUDIO": pipeline.STAGE_HANDLERS["EXTRACTING_AUDIO"]})


@pytest.fixture(scope="module")
def tone(tmp_path_factory):
    path = tmp_path_factory.mktemp("live") / f"tone-{uuid.uuid4().hex[:6]}.mp3"
    # A unique frequency per run keeps the content fingerprint unique across runs.
    frequency = 300 + uuid.uuid4().int % 500
    subprocess.run(
        ["ffmpeg", "-nostdin", "-loglevel", "error", "-y", "-f", "lavfi", "-i", f"sine=frequency={frequency}:duration=3", str(path)],
        check=True,
    )
    return path


@pytest.fixture
def live_settings(tmp_path):
    return Settings(
        _env_file=None,
        supabase_url=_env["SUPABASE_URL"],
        supabase_anon_key=_env["SUPABASE_ANON_KEY"],
        supabase_service_role_key=_env["SUPABASE_SERVICE_ROLE_KEY"],
        work_dir=str(tmp_path / "work"),
    )


@pytest.fixture
async def api(live_settings):
    queue = FakeQueue()
    app.dependency_overrides[get_settings] = lambda: live_settings
    async with app.router.lifespan_context(app):
        app.dependency_overrides[ingestion_api.get_queue] = lambda: queue
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver", timeout=60) as client:
            client.queue = queue
            yield client
    app.dependency_overrides.clear()


def bearer(user):
    return {"Authorization": f"Bearer {user['token']}"}


def service_rows(supa, table, **filters):
    params = {"select": "*", **{key: f"eq.{value}" for key, value in filters.items()}}
    return supa.http.get(f"{supa.url}/rest/v1/{table}", params=params, headers=supa.service_headers()).json()


# --- schema / access control --------------------------------------------------------------


def test_clients_cannot_write_processing_tables(supa, user_a):
    job = {"lecture_id": str(uuid.uuid4()), "user_id": user_a["id"]}
    assert supa.rest("POST", "processing_jobs", user_a["token"], json=job).status_code in (401, 403)
    media = {"lecture_id": str(uuid.uuid4()), "kind": "audio", "storage_path": "x", "mime_type": "audio/flac", "file_size": 1}
    assert supa.rest("POST", "lecture_media", user_a["token"], json=media).status_code in (401, 403)
    assert supa.rest("GET", "processing_jobs", None).status_code in (401, 403)


@pytest.mark.parametrize("function", ["claim_processing_job", "renew_processing_lease", "recover_processing_jobs"])
def test_worker_functions_are_not_callable_by_users(supa, user_a, function):
    args = {"p_job_id": str(uuid.uuid4()), "p_worker": "x", "p_lease_seconds": 60, "p_limit": 1}
    if function == "recover_processing_jobs":
        args = {"p_limit": 1}
    elif function == "renew_processing_lease":
        args.pop("p_limit")
    else:
        args.pop("p_limit")
    response = supa.rest("POST", f"rpc/{function}", user_a["token"], json=args)
    assert response.status_code in (401, 403, 404), response.text


async def test_lease_functions_use_database_time(supa, user_a, live_settings):
    async with httpx.AsyncClient(timeout=30) as http:
        admin = ServiceSupabase(http, live_settings)
        lecture = await admin.insert("lectures", {"user_id": user_a["id"], "title": "Lease test", "source_type": "audio"})
        job = await admin.insert("processing_jobs", {"lecture_id": lecture["id"], "user_id": user_a["id"]})

        first = await admin.rpc("claim_processing_job", {"p_job_id": job["id"], "p_worker": "w1", "p_lease_seconds": 60})
        assert first[0]["status"] == "running" and first[0]["attempt_count"] == 1
        assert await admin.rpc("claim_processing_job", {"p_job_id": job["id"], "p_worker": "w2", "p_lease_seconds": 60}) == []
        assert await admin.rpc("renew_processing_lease", {"p_job_id": job["id"], "p_worker": "w2", "p_lease_seconds": 60}) is False
        assert await admin.rpc("renew_processing_lease", {"p_job_id": job["id"], "p_worker": "w1", "p_lease_seconds": 60}) is True

        expired = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()
        await admin.update("processing_jobs", {"id": f"eq.{job['id']}"}, {"lease_expires_at": expired})
        recovered = await admin.rpc("recover_processing_jobs", {"p_limit": 500})
        assert job["id"] in [row["job_id"] for row in recovered]
        assert service_rows(supa, "processing_jobs", id=job["id"])[0]["status"] == "queued"

        with pytest.raises(Exception):  # a running job must hold a lease (check constraint)
            await admin.update("processing_jobs", {"id": f"eq.{job['id']}"}, {"status": "running"})
        await admin.delete("lectures", {"id": f"eq.{lecture['id']}"})


# --- genuine end-to-end ingestion ------------------------------------------------------------


async def test_upload_process_isolate_retry_and_delete(api, supa, user_a, user_b, tone, live_settings):
    content = tone.read_bytes()
    key = str(uuid.uuid4())

    def post():
        return api.post(
            "/lectures/uploads",
            data={"kind": "audio", "title": "Live pipeline check", "subject": "Testing", "tags": ["phase4"]},
            files={"file": (tone.name, content, "audio/mpeg")},
            headers={**bearer(user_a), "Idempotency-Key": key},
        )

    # 1. Upload -> lecture + media + queued job, file stored privately.
    response = await post()
    assert response.status_code == 202, response.text
    lecture_id = response.json()["lecture"]["id"]
    job_id = response.json()["job"]["id"]
    assert api.queue.items == [job_id]
    original_path = f"{user_a['id']}/{lecture_id}/original/source.mp3"
    assert service_rows(supa, "lecture_media", lecture_id=lecture_id)[0]["storage_path"] == original_path
    assert supa.http.get(f"{supa.url}/storage/v1/object/public/{BUCKET}/{original_path}").status_code >= 400

    # 2. Same submission again is a replay; same content with a new key is a duplicate.
    assert (await post()).status_code == 200
    duplicate = await api.post(
        "/lectures/uploads",
        data={"kind": "audio", "title": "Copy", "subject": "Testing"},
        files={"file": ("copy.mp3", content, "audio/mpeg")},
        headers=bearer(user_a),
    )
    assert duplicate.status_code == 409
    assert len(service_rows(supa, "lectures", user_id=user_a["id"], title="Live pipeline check")) == 1

    # 3. Another user sees nothing and can't act on it.
    assert (await api.get(f"/lectures/{lecture_id}/processing", headers=bearer(user_b))).status_code == 404
    assert (await api.post(f"/lectures/{lecture_id}/retry", headers=bearer(user_b))).status_code == 404
    assert supa.rest("GET", "processing_jobs", user_b["token"], params={"id": f"eq.{job_id}"}).json() == []
    assert supa.storage("GET", f"object/authenticated/{BUCKET}/{original_path}", user_b["token"]).status_code >= 400

    # 4. The real worker processes it with real FFmpeg.
    async with httpx.AsyncClient(timeout=60) as http:
        worker = Worker(live_settings, ServiceSupabase(http, live_settings), FakeQueue(), worker_id="live-test")
        assert await worker.process(job_id) == "waiting"

    details = (await api.get(f"/lectures/{lecture_id}/processing", headers=bearer(user_a))).json()
    assert details["lecture"]["status"] == "TRANSCRIBING"
    assert details["job"]["status"] == "waiting" and details["job"]["current_stage"] == "TRANSCRIBING"
    run = details["stage_runs"][0]
    assert run["stage"] == "EXTRACTING_AUDIO" and run["status"] == "succeeded" and run["duration_ms"] > 0
    # Derived audio is temporary worker data: nothing but the original is stored or listed.
    assert [item["kind"] for item in details["media"]] == ["original"]
    measured = service_rows(supa, "processing_stage_runs", job_id=job_id)[0]["details"]
    assert measured["output_format"] == "flac 16 kHz mono" and 2.5 < measured["output_duration_seconds"] < 3.5
    audio_path = f"{user_a['id']}/{lecture_id}/processed/audio.flac"
    stored = supa.http.post(
        f"{supa.url}/storage/v1/object/list/{BUCKET}",
        headers=supa.service_headers(),
        json={"prefix": f"{user_a['id']}/{lecture_id}/", "limit": 100},
    ).json()
    assert [entry["name"] for entry in stored] == ["original"]
    assert supa.storage("GET", f"object/authenticated/{BUCKET}/{audio_path}", user_a["token"]).status_code >= 400
    listed = (await api.get("/lectures", params={"q": "Live pipeline"}, headers=bearer(user_a))).json()["items"][0]
    assert listed["job"]["status"] == "waiting" and listed["duration_seconds"] == 3

    # 5. Retry is only possible for a retryable failure.
    assert (await api.post(f"/lectures/{lecture_id}/retry", headers=bearer(user_a))).status_code == 409
    supa.http.patch(
        f"{supa.url}/rest/v1/processing_jobs",
        params={"id": f"eq.{job_id}"},
        headers=supa.service_headers(),
        json={"status": "failed", "retryable": True, "error_code": "service_unavailable", "error_message": "x"},
    )
    supa.http.patch(
        f"{supa.url}/rest/v1/lectures", params={"id": f"eq.{lecture_id}"}, headers=supa.service_headers(), json={"status": "FAILED"}
    )
    retried = await api.post(f"/lectures/{lecture_id}/retry", headers=bearer(user_a))
    assert retried.status_code == 200 and retried.json()["status"] == "queued"
    assert service_rows(supa, "lectures", id=lecture_id)[0]["status"] == "QUEUED"

    # 6. Deleting the lecture removes both stored files and every processing record.
    assert (await api.delete(f"/lectures/{lecture_id}", headers=bearer(user_a))).status_code == 204
    leftovers = supa.http.post(
        f"{supa.url}/storage/v1/object/list/{BUCKET}",
        headers=supa.service_headers(),
        json={"prefix": f"{user_a['id']}/{lecture_id}/", "limit": 100},
    ).json()
    assert leftovers == []
    assert service_rows(supa, "processing_jobs", id=job_id) == []
    assert service_rows(supa, "lecture_media", lecture_id=lecture_id) == []


async def test_corrupt_upload_fails_with_a_persisted_reason(api, supa, user_a, live_settings):
    corrupt = b"ID3\x04\x00\x00\x00\x00\x00\x00" + uuid.uuid4().bytes * 64
    response = await api.post(
        "/lectures/uploads",
        data={"kind": "audio", "title": "Corrupt file", "subject": "Testing"},
        files={"file": ("broken.mp3", corrupt, "audio/mpeg")},
        headers=bearer(user_a),
    )
    assert response.status_code == 202, response.text  # the bytes look like MP3; only ffprobe can tell
    lecture_id, job_id = response.json()["lecture"]["id"], response.json()["job"]["id"]

    async with httpx.AsyncClient(timeout=60) as http:
        worker = Worker(live_settings, ServiceSupabase(http, live_settings), FakeQueue(), worker_id="live-test")
        assert await worker.process(job_id) == "failed"

    job = service_rows(supa, "processing_jobs", id=job_id)[0]
    assert job["error_code"] == "media_unreadable" and job["retryable"] is False and job["failed_at"]
    assert service_rows(supa, "lectures", id=lecture_id)[0]["status"] == "FAILED"
    assert (await api.delete(f"/lectures/{lecture_id}", headers=bearer(user_a))).status_code == 204
