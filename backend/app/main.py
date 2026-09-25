"""
LectureMind FastAPI application entrypoint.
"""
import logging
import traceback
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import settings
from app.database import init_db
from app.api.lectures import router as lectures_router
from app.api.auth import router as auth_router

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("lecturemind")

app = FastAPI(
    title="LectureMind API",
    description="Lecture Intelligence System using Whisper, RAG and LLMs",
    version="1.0.0",
)

origins = [o.strip() for o in settings.CORS_ORIGINS.split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def on_startup():
    init_db()
    logger.info(f"LectureMind API started (env={settings.ENV})")


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    # Never leak raw Python stack traces to the client; log server-side only.
    logger.error(f"Unhandled error on {request.url}:\n{traceback.format_exc()}")
    return JSONResponse(
        status_code=500,
        content={"detail": "An unexpected server error occurred. Please try again."},
    )


app.include_router(auth_router)
app.include_router(lectures_router)


@app.get("/")
def root():
    return {"app": settings.APP_NAME, "status": "running", "docs": "/docs"}


@app.get("/api/health")
def health():
    return {"status": "ok"}
