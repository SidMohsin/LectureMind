import uuid

import httpx
import pytest

from app.api import ingestion as ingestion_api
from app.api.deps import get_user_db
from app.core.config import get_settings
from app.core.errors import UpstreamServiceError
from app.main import app
from app.services.ingestion import Ingestion
from app.services.sources import SourceInfo, YouTubeProvider
from app.services.supabase_admin import StorageObjectTooLarge
from app.workers.lifecycle import PIPELINE_STAGES, ProcessingError

from .conftest import make_token
from .fakes import FakeAdmin, FakeQueue

pytestmark = pytest.mark.anyio

USER = str(uuid.uuid4())
OTHER = str(uuid.uuid4())
MP3 = b"ID3\x04\x00\x00\x00\x00\x00\x00" + b"\xff\xfb\x90\x00" * 64
MP4 = b"\x00\x00\x00\x20ftypisom\x00\x00\x02\x00isomiso2mp41" + b"\x00" * 256
PDF = b"%PDF-1.7\n" + b"\x00" * 64


@pytest.fixture
def admin(settings, tmp_path):
    fake = FakeAdmin()
    queue = FakeQueue()
    live = settings.model_copy(update={"supabase_service_role_key": "service", "work_dir": str(tmp_path)})
    app.dependency_overrides[get_settings] = lambda: live
    app.dependency_overrides[ingestion_api.get_ingestion] = lambda: Ingestion(fake, queue)
    fake.queue = queue
    fake.settings = live
    app.state.queue = queue
    app.state.http = httpx.AsyncClient()  # never used for real calls: providers are mocked
    return fake


def auth(user=USER):
    return {"Authorization": f"Bearer {make_token(sub=user)}"}


def upload(client, *, data=None, content=MP3, filename="lecture.mp3", headers=None, kind="audio"):
    fields = {"kind": kind, "title": "Wave-Particle Duality", "subject": "Physics", **(data or {})}
    return client.post(
        "/lectures/uploads", data=fields, files={"file": (filename, content, "application/octet-stream")}, headers={**auth(), **(headers or {})}
    )


# --- file uploads -------------------------------------------------------------------------


async def test_valid_audio_upload_creates_lecture_media_and_queued_job(client, admin):
    response = await upload(client, data={"tags": ["Quantum", "quantum", " Waves "]})

    assert response.status_code == 202, response.text
    body = response.json()
    assert body["lecture"]["status"] == "QUEUED" and body["job"]["status"] == "queued" and not body["replayed"]

    lecture = admin.rows("lectures")[0]
    assert lecture["user_id"] == USER  # from the token, never the request
    assert lecture["source_type"] == "audio" and lecture["tags"] == ["Quantum", "Waves"]
    assert lecture["source_fingerprint"].startswith("sha256:")
    media = admin.rows("lecture_media")[0]
    assert media["storage_path"] == f"{USER}/{lecture['id']}/original/source.mp3"
    assert media["mime_type"] == "audio/mpeg" and media["file_size"] == len(MP3)
    job = admin.rows("processing_jobs")[0]
    assert admin.queue.items == [job["id"]]
    assert admin.storage[f"lectures/{media['storage_path']}"] == MP3


async def test_valid_video_upload_uses_detected_type(client, admin):
    response = await upload(client, kind="video", content=MP4, filename="clip.mp4")
    assert response.status_code == 202
    media = admin.rows("lecture_media")[0]
    assert media["mime_type"] == "video/mp4" and media["storage_path"].endswith("/original/source.mp4")


@pytest.mark.parametrize(
    "kind,content,filename",
    [("audio", PDF, "notes.mp3"), ("video", MP3, "song.mp4"), ("audio", b"<html><script>x</script>", "x.wav")],
    ids=["pdf-renamed-mp3", "audio-as-video", "html"],
)
async def test_content_is_checked_not_the_filename(client, admin, kind, content, filename):
    response = await upload(client, kind=kind, content=content, filename=filename)
    assert response.status_code == 415
    assert response.json()["code"] == "unsupported_media"
    assert admin.rows("lectures") == [] and admin.storage == {}


async def test_oversized_upload_is_rejected_before_anything_is_created(client, admin):
    app.dependency_overrides[get_settings] = lambda: admin.settings.model_copy(update={"max_audio_bytes": 100, "max_video_bytes": 100})
    response = await upload(client, content=MP3 * 2)  # 2 KB > 100 B, within the multipart overhead allowance
    assert response.status_code == 413
    assert admin.rows("lectures") == [] and admin.storage == {}


async def test_body_larger_than_any_limit_is_rejected_from_its_declared_length(client, admin):
    app.dependency_overrides[get_settings] = lambda: admin.settings.model_copy(update={"max_audio_bytes": 10, "max_video_bytes": 10})
    response = await upload(client, content=b"x" * (2 * 1024 * 1024))
    assert response.status_code == 413


@pytest.mark.parametrize(
    "data,message",
    [
        ({"subject": ""}, "Enter the subject"),
        ({"title": ""}, "Enter a lecture title"),
        ({"title": "x" * 301}, "at most 300"),
        ({"tags": [f"t{i}" for i in range(21)]}, "at most 20 tags"),
        ({"lecture_date": "not-a-date"}, "date"),
        ({"kind": "pdf"}, "video or an audio"),
    ],
)
async def test_metadata_is_validated_server_side(client, admin, data, message):
    response = await upload(client, data=data)
    assert response.status_code == 422
    assert message.lower() in response.text.lower()
    assert admin.rows("lectures") == []


async def test_empty_file_is_rejected(client, admin):
    response = await upload(client, content=b"")
    assert response.status_code in (415, 422)
    assert admin.rows("lectures") == []


async def test_upload_requires_authentication(client, admin):
    response = await client.post(
        "/lectures/uploads", data={"kind": "audio", "title": "t", "subject": "s"}, files={"file": ("a.mp3", MP3)}
    )
    assert response.status_code == 401
    assert admin.rows("lectures") == []


async def test_repeated_submission_with_same_key_is_idempotent(client, admin):
    key = str(uuid.uuid4())
    first = await upload(client, headers={"Idempotency-Key": key})
    second = await upload(client, headers={"Idempotency-Key": key})
    assert first.status_code == 202 and second.status_code == 200
    assert second.json()["replayed"] is True
    assert second.json()["lecture"]["id"] == first.json()["lecture"]["id"]
    assert len(admin.rows("lectures")) == 1 and len(admin.rows("processing_jobs")) == 1
    assert len(admin.queue.items) == 1


async def test_same_content_twice_is_reported_as_duplicate(client, admin):
    first = await upload(client)
    second = await upload(client, filename="renamed-copy.mp3")
    assert second.status_code == 409
    assert second.json()["code"] == "duplicate_lecture"
    assert second.json()["details"]["lecture_id"] == first.json()["lecture"]["id"]
    assert len(admin.rows("lectures")) == 1


async def test_same_content_for_different_users_is_independent(client, admin):
    assert (await upload(client)).status_code == 202
    other = await client.post(
        "/lectures/uploads",
        data={"kind": "audio", "title": "t", "subject": "s"},
        files={"file": ("a.mp3", MP3)},
        headers=auth(OTHER),
    )
    assert other.status_code == 202
    assert {row["user_id"] for row in admin.rows("lectures")} == {USER, OTHER}


async def test_hostile_filename_never_reaches_storage_paths(client, admin):
    response = await upload(client, filename="..\\..\\etc/passwd.mp3")
    assert response.status_code == 202
    lecture = admin.rows("lectures")[0]
    assert lecture["original_filename"] == "passwd.mp3"
    assert admin.rows("lecture_media")[0]["storage_path"] == f"{USER}/{lecture['id']}/original/source.mp3"


@pytest.mark.parametrize(
    "failure,status",
    [(UpstreamServiceError(), 502), (StorageObjectTooLarge(), 413)],
    ids=["storage-down", "storage-plan-limit"],
)
async def test_storage_failure_leaves_nothing_behind(client, admin, failure, status):
    admin.fail_upload = failure
    response = await upload(client)
    assert response.status_code == status
    assert admin.rows("lectures") == [] and admin.rows("processing_jobs") == []


async def test_queue_outage_does_not_block_submission(client, admin):
    admin.queue.fail = True
    response = await upload(client)
    assert response.status_code == 202
    assert admin.rows("processing_jobs")[0]["status"] == "queued"  # the worker's sweep will find it


async def test_ingestion_unavailable_without_service_key(client, settings):
    app.dependency_overrides.pop(ingestion_api.get_ingestion, None)
    app.dependency_overrides[get_settings] = lambda: settings
    response = await client.post(
        "/lectures/uploads", data={"kind": "audio"}, files={"file": ("a.mp3", MP3)}, headers=auth()
    )
    assert response.status_code == 503


# --- source URLs ---------------------------------------------------------------------------


@pytest.fixture
def youtube(monkeypatch):
    calls = []

    async def check_access(self, ref, http):
        calls.append(ref)
        outcome = check_access.outcome
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    check_access.outcome = SourceInfo(title="MIT 6.006 Lecture 1: Algorithms", author="MIT OpenCourseWare")
    monkeypatch.setattr(YouTubeProvider, "check_access", check_access)
    return check_access, calls


def submit(client, url="https://youtu.be/ZA-tUyM_y7s?t=30", **extra):
    body = {"url": url, "subject": "Computer Science", "rights_confirmed": True, **extra}
    return client.post("/lectures/sources", json=body, headers={**auth(), **extra.pop("headers", {})})


async def test_supported_url_is_accepted_with_source_metadata(client, admin, youtube):
    response = await submit(client)
    assert response.status_code == 202, response.text
    lecture = admin.rows("lectures")[0]
    assert lecture["source_type"] == "url"
    assert lecture["source_url"] == "https://www.youtube.com/watch?v=ZA-tUyM_y7s"
    assert lecture["source_fingerprint"] == "youtube:ZA-tUyM_y7s"
    assert lecture["title"] == "MIT 6.006 Lecture 1: Algorithms"  # from the availability check
    assert lecture["instructor"] == "MIT OpenCourseWare"
    assert lecture["source_rights_confirmed_at"]
    assert admin.queue.items == [admin.rows("processing_jobs")[0]["id"]]


@pytest.mark.parametrize(
    "url,status,code",
    [
        ("not a url", 422, "validation_error"),
        ("ftp://youtube.com/watch?v=ZA-tUyM_y7s", 422, "validation_error"),
        ("https://vimeo.com/123456", 422, "unsupported_source"),
        ("https://www.youtube.com/@mitocw", 422, "unsupported_source"),
        ("https://www.youtube.com/watch?v=short", 422, "unsupported_source"),
        ("https://evil.example/watch?v=ZA-tUyM_y7s", 422, "unsupported_source"),
    ],
)
async def test_malformed_and_unsupported_urls_are_rejected(client, admin, youtube, url, status, code):
    response = await submit(client, url=url)
    assert response.status_code == status
    assert response.json()["code"] == code
    assert admin.rows("lectures") == [] and youtube[1] == []


@pytest.mark.parametrize(
    "error,status",
    [
        (ProcessingError("source_restricted", "private"), 422),
        (ProcessingError("source_not_found", "gone"), 422),
        (ProcessingError("source_check_failed", "down", retryable=True), 503),
    ],
)
async def test_inaccessible_sources_fail_clearly(client, admin, youtube, error, status):
    youtube[0].outcome = error
    response = await submit(client)
    assert response.status_code == status
    assert response.json()["code"] == error.code
    assert admin.rows("lectures") == []


async def test_rights_confirmation_is_required(client, admin, youtube):
    response = await submit(client, rights_confirmed=False)
    assert response.status_code == 422 and response.json()["code"] == "rights_not_confirmed"


async def test_same_video_twice_is_a_duplicate(client, admin, youtube):
    await submit(client)
    again = await submit(client, url="https://www.youtube.com/watch?v=ZA-tUyM_y7s&list=PL1")
    assert again.status_code == 409
    assert len(admin.rows("lectures")) == 1


# --- retry --------------------------------------------------------------------------------


async def seed_failed(admin, *, owner=USER, retryable=True):
    lecture = await admin.insert("lectures", {"user_id": owner, "title": "L", "status": "FAILED", "source_type": "audio"})
    job = await admin.insert(
        "processing_jobs",
        {
            "lecture_id": lecture["id"], "user_id": owner, "status": "failed", "attempt_count": 3,
            "retryable": retryable, "error_code": "service_unavailable", "error_message": "x",
        },
    )
    return lecture, job


async def test_retry_requeues_a_failed_job_once(client, admin):
    lecture, job = await seed_failed(admin)
    response = await client.post(f"/lectures/{lecture['id']}/retry", headers=auth())
    assert response.status_code == 200
    stored = admin.rows("processing_jobs")[0]
    assert stored["status"] == "queued" and stored["error_code"] is None and stored["max_attempts"] == 6
    assert admin.rows("lectures")[0]["status"] == "QUEUED"
    assert admin.queue.items == [job["id"]]

    again = await client.post(f"/lectures/{lecture['id']}/retry", headers=auth())
    assert again.status_code == 409  # no double queueing


async def test_non_retryable_failure_cannot_be_retried(client, admin):
    lecture, _ = await seed_failed(admin, retryable=False)
    response = await client.post(f"/lectures/{lecture['id']}/retry", headers=auth())
    assert response.status_code == 409
    assert admin.rows("processing_jobs")[0]["status"] == "failed"


async def test_cannot_retry_another_users_job(client, admin):
    lecture, _ = await seed_failed(admin, owner=OTHER)
    response = await client.post(f"/lectures/{lecture['id']}/retry", headers=auth(USER))
    assert response.status_code == 404
    assert admin.rows("processing_jobs")[0]["status"] == "failed"


async def test_retry_rejects_tampered_ids(client, admin):
    assert (await client.post("/lectures/not-a-uuid/retry", headers=auth())).status_code == 422
    assert (await client.post(f"/lectures/{uuid.uuid4()}/retry", headers=auth())).status_code == 404


# --- processing details + limits --------------------------------------------------------------


class UserDb:
    """User-scoped reads (RLS): only rows of the token's user are visible."""

    def __init__(self, admin, user_id):
        self.admin, self.user_id = admin, user_id

    async def select(self, table, params):
        rows = await self.admin.select(table, params)
        if table == "lectures":
            return [r for r in rows if r["user_id"] == self.user_id]
        if table == "processing_jobs":
            return [r for r in rows if r["user_id"] == self.user_id]
        return rows


async def test_processing_details_for_owner_only(client, admin):
    lecture, job = await seed_failed(admin)
    admin.add("processing_stage_runs", job_id=job["id"], stage="EXTRACTING_AUDIO", attempt=1, status="failed",
              started_at="2026-10-01T00:00:00Z", finished_at=None, duration_ms=1200, error_code="service_unavailable")

    app.dependency_overrides[get_user_db] = lambda: UserDb(admin, USER)
    response = await client.get(f"/lectures/{lecture['id']}/processing", headers=auth())
    assert response.status_code == 200
    body = response.json()
    assert body["job"]["status"] == "failed" and body["stage_runs"][0]["duration_ms"] == 1200
    assert body["implemented_stages"] == list(PIPELINE_STAGES)

    app.dependency_overrides[get_user_db] = lambda: UserDb(admin, OTHER)
    assert (await client.get(f"/lectures/{lecture['id']}/processing", headers=auth(OTHER))).status_code == 404


async def test_limits_come_from_server_configuration(client, admin):
    response = await client.get("/ingestion/limits", headers=auth())
    assert response.status_code == 200
    body = response.json()
    assert body["video"]["max_bytes"] == admin.settings.max_video_bytes
    assert body["source_providers"] == ["youtube"]


async def test_api_stays_responsive_while_upload_is_handled(client, admin):
    # Processing is not done in the request: submission returns with the job merely queued.
    response = await upload(client)
    assert response.json()["job"]["status"] == "queued"
    assert not any(call[0] == "download" for call in admin.calls)
    assert (await client.get("/health")).status_code == 200

