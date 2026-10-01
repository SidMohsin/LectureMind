import logging
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import api_router
from app.core.config import get_settings
from app.core.errors import register_error_handlers
from app.core.logging import configure_logging
from app.core.observability import RequestContextMiddleware
from app.core.rate_limit import RateLimiter
from app.services.queue import RedisJobQueue

settings = get_settings()
configure_logging()
logger = logging.getLogger(__name__)


def checked_cors_origins() -> list[str]:
    """Explicit origins only; production additionally requires HTTPS origins."""
    origins = settings.cors_origins_list
    if "*" in origins:
        raise RuntimeError("CORS_ALLOW_ORIGINS must list explicit origins, not '*'.")
    if settings.is_production and any(not origin.startswith("https://") for origin in origins):
        raise RuntimeError("In production, every CORS_ALLOW_ORIGINS entry must be an https:// origin.")
    return origins


@asynccontextmanager
async def lifespan(app: FastAPI):
    if not settings.supabase_configured:
        logger.warning("SUPABASE_URL / SUPABASE_ANON_KEY are not set; authenticated endpoints will return 503.")
    if not settings.ingestion_configured:
        logger.warning("SUPABASE_SERVICE_ROLE_KEY is not set; lecture ingestion endpoints will return 503.")
    app.state.http = httpx.AsyncClient(timeout=10.0)
    # Both connect lazily: the API starts (and keeps serving) even if Redis is down.
    app.state.queue = RedisJobQueue(settings.redis_url, settings.queue_name)
    app.state.rate_limiter = RateLimiter.from_url(settings.redis_url)
    try:
        yield
    finally:
        await app.state.rate_limiter.close()
        await app.state.queue.close()
        await app.state.http.aclose()


# Interactive API docs are a development aid; production doesn't expose them.
docs = {} if not settings.is_production else {"docs_url": None, "redoc_url": None, "openapi_url": None}
app = FastAPI(title=settings.app_name, lifespan=lifespan, **docs)

app.add_middleware(
    CORSMiddleware,
    allow_origins=checked_cors_origins(),
    allow_credentials=False,  # bearer tokens, not cookies
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "Idempotency-Key", "X-Request-ID"],
    expose_headers=["X-Request-ID", "Retry-After"],
)
# Outermost: correlation id, security headers and request logging for every response.
app.add_middleware(RequestContextMiddleware, hsts=settings.is_production)

register_error_handlers(app)

app.include_router(api_router)
