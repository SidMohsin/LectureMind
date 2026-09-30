"""The job queue against a real Redis server (skipped when none is reachable)."""

import socket
import uuid

import pytest

from app.core.config import Settings
from app.services.queue import RedisJobQueue

pytestmark = [pytest.mark.anyio, pytest.mark.integration]


def _redis_reachable() -> bool:
    try:
        with socket.create_connection(("localhost", 6379), timeout=1):
            return True
    except OSError:
        return False


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.mark.skipif(not _redis_reachable(), reason="no Redis server on localhost:6379")
async def test_queue_round_trip_on_real_redis():
    # Uses RESP2, so it also works with Redis servers older than 6 (no HELLO command).
    name = f"lecturemind:test:{uuid.uuid4().hex}"
    queue = RedisJobQueue(Settings(_env_file=None).redis_url, name)
    try:
        assert await queue.ping()
        await queue.enqueue("job-1")
        await queue.enqueue("job-2", dedupe_seconds=5)
        await queue.enqueue("job-2", dedupe_seconds=5)
        assert [await queue.dequeue(1) for _ in range(3)] == ["job-1", "job-2", None]
    finally:
        await queue._redis.delete(name, f"{name}:notified:job-2")
        await queue.close()


@pytest.mark.skipif(not _redis_reachable(), reason="no Redis server on localhost:6379")
async def test_idle_wait_is_not_reported_as_a_timeout():
    # The worker waits the full blocking period when there's no work; that must
    # return None, not raise a socket read timeout.
    queue = RedisJobQueue(Settings(_env_file=None).redis_url, f"lecturemind:test:{uuid.uuid4().hex}")
    try:
        assert await queue.dequeue(timeout_seconds=5) is None
    finally:
        await queue.close()
