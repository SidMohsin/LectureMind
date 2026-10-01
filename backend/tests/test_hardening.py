"""Phase 7B hardening: rate limits, security headers, correlation ids, readiness, safe logs,
worker presence and stuck-job detection, job recovery limits, and orphan cleanup safety."""

import logging
import uuid
from datetime import datetime, timedelta, timezone

import pytest

from app.api import workspace as workspace_api
from app.api.deps import get_user_db
from app.core.errors import upstream_error_summary
from app.core.rate_limit import Limit, RateLimiter
from app.main import app
from app.workers.main import Worker
from app.workers.maintenance import classify

from .conftest import make_token
from .fakes import FakeAdmin, FakeQueue

pytestmark = pytest.mark.anyio

USER_ID = str(uuid.uuid4())


class FakeRedis:
    """Just enough of redis.asyncio for the fixed-window limiter."""

    def __init__(self, fail=False):
        self.values: dict[str, int] = {}
        self.ttl: dict[str, int] = {}
        self.fail = fail

    def pipeline(self, transaction=True):
        redis = self

        class Pipe:
            def __init__(self):
                self.ops = []

            async def __aenter__(self):
                return self

            async def __aexit__(self, *exc):
                return False

            def incr(self, key):
                self.ops.append(("incr", key))

            def expire(self, key, seconds):
                self.ops.append(("expire", key, seconds))

            async def execute(self):
                if redis.fail:
                    raise ConnectionError("redis down")
                results = []
                for op in self.ops:
                    if op[0] == "incr":
                        redis.values[op[1]] = redis.values.get(op[1], 0) + 1
                        results.append(redis.values[op[1]])
                    else:
                        redis.ttl[op[1]] = op[2]
                        results.append(True)
                return results

        return Pipe()

    async def aclose(self):
        pass


# --- rate limiting ---------------------------------------------------------------------------


async def test_fixed_window_limit_per_user_and_operation():
    limiter = RateLimiter(FakeRedis())
    limit = Limit.parse("3/60")
    results = [await limiter.hit("questions", "user-a", limit, now=1000.0) for _ in range(4)]
    assert [r.allowed for r in results] == [True, True, True, False]
    assert results[-1].retry_after == 20  # window 960-1020
    assert (await limiter.hit("questions", "user-b", limit, now=1000.0)).allowed  # other user unaffected
    assert (await limiter.hit("search", "user-a", limit, now=1000.0)).allowed  # other operation unaffected
    assert (await limiter.hit("questions", "user-a", limit, now=1021.0)).allowed  # next window


def test_limit_parsing_and_validation():
    from app.core.config import Settings

    assert Limit.parse("") is None and Limit.parse("20/300") == Limit(20, 300)
    with pytest.raises(ValueError):
        Settings(_env_file=None, rate_limit_questions="lots")
    assert Settings(_env_file=None, rate_limit_questions="").rate_limit_questions == ""


class SearchDb:
    async def rpc(self, function, args):
        return []


class Embedder:
    name = "BAAI/bge-small-en-v1.5"
    dimension = 384

    def embed_query(self, text):
        return [0.0] * 384


@pytest.fixture
def search_env(settings):
    app.dependency_overrides[get_user_db] = lambda: SearchDb()
    app.dependency_overrides[workspace_api.get_embedder] = lambda: Embedder()
    yield
    app.state.rate_limiter = None


async def test_endpoint_returns_429_with_retry_after(client, settings, search_env):
    settings.rate_limit_search = "2/60"
    app.state.rate_limiter = RateLimiter(FakeRedis())
    auth = {"Authorization": f"Bearer {make_token(sub=USER_ID)}"}
    codes = [(await client.get("/search/content", params={"q": "gradient descent"}, headers=auth)).status_code for _ in range(3)]
    assert codes == [200, 200, 429]
    blocked = await client.get("/search/content", params={"q": "gradient descent"}, headers=auth)
    assert blocked.json()["code"] == "rate_limited" and int(blocked.headers["retry-after"]) > 0
    other = {"Authorization": f"Bearer {make_token(sub=str(uuid.uuid4()))}"}
    assert (await client.get("/search/content", params={"q": "gradient descent"}, headers=other)).status_code == 200


async def test_rate_limit_fails_open_when_redis_is_down(client, settings, search_env, caplog):
    settings.rate_limit_search = "1/60"
    app.state.rate_limiter = RateLimiter(FakeRedis(fail=True))
    auth = {"Authorization": f"Bearer {make_token(sub=USER_ID)}"}
    with caplog.at_level(logging.WARNING):
        codes = [(await client.get("/search/content", params={"q": "gradient descent"}, headers=auth)).status_code for _ in range(3)]
    assert codes == [200, 200, 200]
    assert "rate_limit_unavailable" in caplog.text


async def test_unauthenticated_requests_are_rejected_before_counting(client, settings, search_env):
    redis = FakeRedis()
    app.state.rate_limiter = RateLimiter(redis)
    assert (await client.get("/search/content", params={"q": "gradient"})).status_code == 401
    assert redis.values == {}


# --- headers, correlation, logging ------------------------------------------------------------


async def test_security_headers_and_request_id(client, settings):
    response = await client.get("/health")
    headers = response.headers
    assert headers["x-content-type-options"] == "nosniff" and headers["x-frame-options"] == "DENY"
    assert headers["referrer-policy"] == "no-referrer" and headers["cache-control"] == "no-store"
    assert "default-src 'none'" in headers["content-security-policy"]
    assert len(headers["x-request-id"]) == 32
    echoed = await client.get("/health", headers={"X-Request-ID": "client-supplied-id-123"})
    assert echoed.headers["x-request-id"] == "client-supplied-id-123"
    rejected = await client.get("/health", headers={"X-Request-ID": "bad id with spaces\nand newline"})
    assert rejected.headers["x-request-id"] != "bad id with spaces\nand newline"


async def test_request_log_has_route_template_not_query_text(client, settings, caplog):
    with caplog.at_level(logging.INFO, logger="app.requests"):
        await client.get("/search/content", params={"q": "my private search words"})
    line = next(r.getMessage() for r in caplog.records if r.name == "app.requests")
    assert "route=/search/content" in line and "status=401" in line and "private" not in caplog.text


def test_upstream_error_summary_drops_row_details():
    body = '{"code":"23514","details":"Failing row contains (secret question text)","message":"violates check constraint","hint":null}'
    summary = upstream_error_summary(body)
    assert "secret" not in summary and "code=23514" in summary and "violates check constraint" in summary
    assert upstream_error_summary("<html>gateway</html>") == "<non-json body, 20 chars>"


async def test_unhandled_errors_are_generic(settings):
    import httpx

    @app.get("/__boom")
    async def boom():
        raise RuntimeError("internal detail: service key abc123")

    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    try:
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            response = await client.get("/__boom")
        assert response.status_code == 500 and response.json() == {
            "message": "An unexpected error occurred.", "code": "internal_error", "details": None
        }
        assert "abc123" not in response.text
    finally:
        app.router.routes = [r for r in app.router.routes if getattr(r, "path", "") != "/__boom"]


# --- readiness --------------------------------------------------------------------------------


class ReadyAdmin:
    def __init__(self, ok=True):
        self.ok = ok

    async def select(self, table, params):
        if not self.ok:
            raise ConnectionError("db down")
        return []


@pytest.fixture
def readiness(settings, monkeypatch):
    from app.api import health

    settings.supabase_service_role_key = "service-key"
    state = {"admin": ReadyAdmin(), "queue": FakeQueue()}
    monkeypatch.setattr(health, "ServiceSupabase", lambda http, settings: state["admin"])
    app.state.queue = state["queue"]
    app.state.http = None
    return state


async def test_ready_when_everything_is_up(client, readiness):
    readiness["queue"].workers["w1"] = {"worker_id": "w1", "busy": True}
    body = (await client.get("/health/ready")).json()
    assert body["status"] == "ok"
    assert body["checks"]["workers"] == {"ok": True, "count": 1, "busy": 1}


async def test_degraded_without_redis_or_workers_but_still_ready(client, readiness):
    readiness["queue"].fail = True
    response = await client.get("/health/ready")
    assert response.status_code == 200 and response.json()["status"] == "degraded"
    assert response.json()["checks"]["redis"]["ok"] is False


async def test_unready_without_database(client, readiness):
    readiness["admin"].ok = False
    response = await client.get("/health/ready")
    assert response.status_code == 503 and response.json()["status"] == "unavailable"
    assert "db down" not in response.text


# --- worker reliability ----------------------------------------------------------------------


def _job(**overrides):
    return {
        "id": str(uuid.uuid4()), "lecture_id": str(uuid.uuid4()), "user_id": USER_ID, "status": "queued",
        "current_stage": "TRANSCRIBING", "attempt_count": 0, "max_attempts": 3, "next_attempt_at": datetime.now(timezone.utc).isoformat(),
        "lease_owner": None, "lease_expires_at": None, "started_at": None, "updated_at": datetime.now(timezone.utc).isoformat(), **overrides,
    }


@pytest.fixture
def worker(settings):
    settings.supabase_service_role_key = "k"
    admin, queue = FakeAdmin(), FakeQueue()
    return Worker(settings, admin, queue, worker_id="worker-test")


async def test_worker_announces_presence(worker):
    await worker.announce()
    info = worker.queue.workers["worker-test"]
    assert info["worker_id"] == "worker-test" and info["busy"] is False


async def test_stuck_jobs_are_detected_and_logged(worker, caplog):
    old = (datetime.now(timezone.utc) - timedelta(hours=10)).isoformat()
    overdue = worker.admin.add("processing_jobs", **_job(next_attempt_at=old))
    fresh = worker.admin.add("processing_jobs", **_job())
    long_running = worker.admin.add("processing_jobs", **_job(status="running", started_at=old))
    with caplog.at_level(logging.WARNING):
        found = await worker.find_stuck_jobs()
    assert found["queued_overdue"] == [overdue["id"]] and found["long_running"] == [long_running["id"]]
    assert fresh["id"] not in found["queued_overdue"] and "stuck_job kind=queued_overdue" in caplog.text


async def test_abandoned_job_out_of_attempts_is_failed_not_requeued(worker):
    past = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()
    lecture = worker.admin.add("lectures", id=str(uuid.uuid4()), user_id=USER_ID, status="TRANSCRIBING", source_type="audio")
    exhausted = worker.admin.add("processing_jobs", **_job(lecture_id=lecture["id"], status="running", attempt_count=3, lease_owner="dead", lease_expires_at=past))
    retryable = worker.admin.add("processing_jobs", **_job(status="running", attempt_count=1, lease_owner="dead", lease_expires_at=past))
    due = await worker.recover()
    assert exhausted["id"] not in due and retryable["id"] in due
    assert worker.admin.rows("processing_jobs", id=exhausted["id"])[0]["status"] == "failed"
    assert worker.admin.rows("processing_jobs", id=exhausted["id"])[0]["error_code"] == "processing_interrupted"
    assert worker.admin.rows("lectures", id=lecture["id"])[0]["status"] == "FAILED"


# --- cleanup safety --------------------------------------------------------------------------


def test_orphan_classification_is_conservative():
    owner, lecture = str(uuid.uuid4()), str(uuid.uuid4())
    cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
    old = (cutoff - timedelta(hours=1)).isoformat()
    recent = (cutoff + timedelta(hours=1)).isoformat()
    lectures = {lecture: owner}
    referenced = {f"{owner}/{lecture}/original/source.mp4"}
    keep = classify(f"{owner}/{lecture}/original/source.mp4", {"created_at": old}, lectures, referenced, cutoff=cutoff)
    assert keep is None
    assert classify(f"{owner}/{uuid.uuid4()}/processed/playback.m4a", {"created_at": old}, lectures, referenced, cutoff=cutoff).reason == "lecture_missing"
    assert classify(f"{owner}/{lecture}/processed/audio.flac", {"created_at": old}, lectures, referenced, cutoff=cutoff).reason == "unreferenced"
    assert classify(f"{uuid.uuid4()}/{lecture}/original/x.mp4", {"created_at": old}, lectures, referenced, cutoff=cutoff).reason == "owner_mismatch"
    # Recent or undated objects are never touched (an upload may be in progress).
    assert classify(f"{owner}/{uuid.uuid4()}/processed/playback.m4a", {"created_at": recent}, lectures, referenced, cutoff=cutoff) is None
    assert classify(f"{owner}/{uuid.uuid4()}/processed/playback.m4a", {}, lectures, referenced, cutoff=cutoff) is None


def test_stale_workspace_cleanup_only_removes_old_job_directories(tmp_path):
    import os
    import time

    from app.workers.workspace import remove_stale_workspaces

    old_job, new_job, other = tmp_path / "job-old", tmp_path / "job-new", tmp_path / "keep-me"
    for directory in (old_job, new_job, other):
        directory.mkdir()
    past = time.time() - 7200
    os.utime(old_job, (past, past))
    os.utime(other, (past, past))
    assert remove_stale_workspaces(tmp_path, older_than_seconds=3600) == 1
    assert not old_job.exists() and new_job.exists() and other.exists()
