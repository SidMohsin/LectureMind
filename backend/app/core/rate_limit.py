"""Per-user rate limits for expensive operations (questions, search, uploads, URL ingestion).

Fixed-window counters in the existing Redis server: one key per user, operation and
window, incremented atomically and expired with the window. Limits come from settings
as "<requests>/<seconds>". The user id comes from the verified access token only.

If Redis can't be reached the request is allowed and a warning is logged: Redis is a
notification and coordination aid in this architecture, and an outage must not take
the product down. (Authorization never depends on Redis.)
"""

import logging
import time
from dataclasses import dataclass

import redis.asyncio as redis
from fastapi import Depends, Request, status

from app.api.deps import get_current_user
from app.core.config import Settings, get_settings
from app.core.errors import AppError
from app.core.security import AuthenticatedUser

logger = logging.getLogger(__name__)

KEY_PREFIX = "lecturemind:ratelimit"


@dataclass(frozen=True)
class Limit:
    requests: int
    window_seconds: int

    @classmethod
    def parse(cls, value: str) -> "Limit | None":
        if not value:
            return None
        count, _, window = value.partition("/")
        return cls(int(count), int(window))


@dataclass(frozen=True)
class Decision:
    allowed: bool
    remaining: int
    retry_after: int


class RateLimiter:
    def __init__(self, client):
        self._redis = client

    @classmethod
    def from_url(cls, url: str) -> "RateLimiter":
        return cls(redis.from_url(url, decode_responses=True, protocol=2, socket_connect_timeout=2, socket_timeout=2))

    async def hit(self, operation: str, subject: str, limit: Limit, *, now: float | None = None) -> Decision:
        now = time.time() if now is None else now
        window = int(now // limit.window_seconds)
        key = f"{KEY_PREFIX}:{operation}:{subject}:{window}"
        async with self._redis.pipeline(transaction=True) as pipe:
            pipe.incr(key)
            pipe.expire(key, limit.window_seconds + 1)
            count, _ = await pipe.execute()
        retry_after = max(1, int((window + 1) * limit.window_seconds - now))
        return Decision(allowed=count <= limit.requests, remaining=max(0, limit.requests - count), retry_after=retry_after)

    async def close(self) -> None:
        await self._redis.aclose()


def rate_limited(operation: str, setting: str):
    """Dependency enforcing `settings.<setting>` for the calling user."""

    async def dependency(
        request: Request,
        user: AuthenticatedUser = Depends(get_current_user),
        settings: Settings = Depends(get_settings),
    ) -> None:
        limit = Limit.parse(getattr(settings, setting))
        limiter: RateLimiter | None = getattr(request.app.state, "rate_limiter", None)
        if limit is None or limiter is None:
            return
        try:
            decision = await limiter.hit(operation, str(user.id), limit)
        except Exception as exc:  # noqa: BLE001 - fail open; see module docstring
            logger.warning("rate_limit_unavailable operation=%s error=%s", operation, type(exc).__name__)
            return
        if not decision.allowed:
            logger.info("rate_limited operation=%s retry_after=%s", operation, decision.retry_after)
            raise AppError(
                status.HTTP_429_TOO_MANY_REQUESTS,
                "rate_limited",
                f"Too many requests. Please wait {decision.retry_after} seconds and try again.",
                details={"retry_after": decision.retry_after},
                headers={"Retry-After": str(decision.retry_after)},
            )

    return dependency
