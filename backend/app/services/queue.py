"""Job notification queue.

Redis carries only job ids ("this job may be ready to run"). The database row
is the source of truth: a worker must still claim the job there, so duplicate
or stale messages are harmless and lost messages are recovered by the
worker's periodic database sweep. Only basic list/string commands are used,
so any Redis server (including older Windows ports) works.
"""

import json
from typing import Protocol

import redis.asyncio as redis

MAX_BLOCKING_SECONDS = 5


class JobQueue(Protocol):
    async def enqueue(self, job_id: str, *, dedupe_seconds: int = 0) -> None: ...

    async def dequeue(self, timeout_seconds: int) -> str | None: ...

    async def ping(self) -> bool: ...

    async def announce_worker(self, worker_id: str, info: dict, ttl_seconds: int) -> None: ...

    async def active_workers(self) -> list[dict]: ...

    async def close(self) -> None: ...


class RedisJobQueue:
    def __init__(self, url: str, name: str):
        # protocol=2 (RESP2): newer clients otherwise open with HELLO (RESP3), which
        # Redis servers older than 6 reject.
        # socket_timeout must exceed the longest blocking BRPOP wait, or an idle
        # wait is reported as a read timeout instead of "no job yet".
        self._redis = redis.from_url(
            url,
            decode_responses=True,
            protocol=2,
            socket_connect_timeout=5,
            socket_timeout=MAX_BLOCKING_SECONDS + 25,
            health_check_interval=30,
        )
        self._name = name

    async def enqueue(self, job_id: str, *, dedupe_seconds: int = 0) -> None:
        # dedupe_seconds suppresses repeat notifications from the recovery sweep.
        if dedupe_seconds and not await self._redis.set(f"{self._name}:notified:{job_id}", "1", nx=True, ex=dedupe_seconds):
            return
        await self._redis.lpush(self._name, job_id)

    async def dequeue(self, timeout_seconds: int) -> str | None:
        item = await self._redis.brpop([self._name], timeout=min(timeout_seconds, MAX_BLOCKING_SECONDS))
        return item[1] if item else None

    async def ping(self) -> bool:
        return bool(await self._redis.ping())

    # Worker presence: each worker refreshes a key that expires on its own, so a dead
    # worker disappears within ttl_seconds without any cleanup.
    async def announce_worker(self, worker_id: str, info: dict, ttl_seconds: int) -> None:
        await self._redis.set(f"{self._name}:worker:{worker_id}", json.dumps(info), ex=ttl_seconds)

    async def active_workers(self) -> list[dict]:
        keys = [key async for key in self._redis.scan_iter(match=f"{self._name}:worker:*", count=100)]
        values = await self._redis.mget(keys) if keys else []
        return [json.loads(value) for value in values if value]

    async def close(self) -> None:
        await self._redis.aclose()
