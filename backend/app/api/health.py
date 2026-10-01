"""Liveness and readiness.

/health        liveness: the process is up (no dependencies touched).
/health/ready  readiness: the database answers (required, otherwise 503), plus the state
               of Redis and of the processing workers. Redis or workers being down
               degrades the service (processing waits; the database sweep recovers
               jobs) but doesn't make the API unready. Only booleans and counts are
               returned: no hostnames, versions or error text.
"""

import asyncio
import time

from fastapi import APIRouter, Request, Response, status

from app.core.config import get_settings
from app.services.supabase_admin import ServiceSupabase

router = APIRouter(tags=["health"])

CHECK_TIMEOUT_SECONDS = 3.0


@router.get("/health")
def get_health():
    settings = get_settings()
    return {
        "status": "ok",
        "service": settings.app_name,
        "environment": settings.environment,
    }


async def _database_ok(request: Request) -> bool:
    settings = get_settings()
    if not settings.ingestion_configured:
        return False
    admin = ServiceSupabase(request.app.state.http, settings)
    await admin.select("processing_jobs", {"select": "id", "limit": "1"})
    return True


async def _check(probe) -> tuple[bool, int]:
    started = time.monotonic()
    try:
        ok = bool(await asyncio.wait_for(probe, CHECK_TIMEOUT_SECONDS))
    except Exception:  # noqa: BLE001 - any failure means "not ok"; details stay in the logs of the probe
        ok = False
    return ok, int((time.monotonic() - started) * 1000)


@router.get("/health/ready")
async def get_readiness(request: Request, response: Response):
    queue = request.app.state.queue
    database, database_ms = await _check(_database_ok(request))
    redis_ok, redis_ms = await _check(queue.ping())
    workers: list[dict] = []
    if redis_ok:
        try:
            workers = await asyncio.wait_for(queue.active_workers(), CHECK_TIMEOUT_SECONDS)
        except Exception:  # noqa: BLE001
            workers = []

    if not database:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    healthy = database and redis_ok and bool(workers)
    return {
        "status": "ok" if healthy else ("degraded" if database else "unavailable"),
        "checks": {
            "database": {"ok": database, "ms": database_ms},
            "redis": {"ok": redis_ok, "ms": redis_ms},
            "workers": {"ok": bool(workers), "count": len(workers), "busy": sum(1 for w in workers if w.get("busy"))},
        },
    }
