import logging
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import api_router
from app.core.config import get_settings
from app.core.errors import register_error_handlers
from app.core.logging import configure_logging
from app.services.queue import RedisJobQueue

settings = get_settings()
configure_logging()
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    if not settings.supabase_configured:
        logger.warning("SUPABASE_URL / SUPABASE_ANON_KEY are not set; authenticated endpoints will return 503.")
    if not settings.ingestion_configured:
        logger.warning("SUPABASE_SERVICE_ROLE_KEY is not set; lecture ingestion endpoints will return 503.")
    app.state.http = httpx.AsyncClient(timeout=10.0)
    # Connects lazily: the API starts (and keeps serving) even if Redis is down.
    app.state.queue = RedisJobQueue(settings.redis_url, settings.queue_name)
    try:
        yield
    finally:
        await app.state.queue.close()
        await app.state.http.aclose()


app = FastAPI(title=settings.app_name, lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "Idempotency-Key"],
)

register_error_handlers(app)

app.include_router(api_router)
