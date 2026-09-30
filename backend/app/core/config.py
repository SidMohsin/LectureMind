"""Centralized application configuration.

All configuration is loaded from environment variables (see .env.example).
Nothing here should be hard-coded per environment; environment separation is
achieved by pointing each deployment at its own .env / process environment.
"""

import tempfile
from functools import lru_cache
from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # General
    environment: str = "development"
    app_name: str = "LectureMind API"
    log_level: str = "INFO"

    # CORS
    cors_allow_origins: str = "http://localhost:5173"

    # Supabase. The anon (publishable) key is enough for the backend: every
    # data request is forwarded with the caller's own access token, so Row Level
    # Security applies to backend queries exactly as it does to the user.
    supabase_url: str = ""
    supabase_anon_key: str = ""
    # Only needed for projects still signing tokens with the legacy shared
    # HS256 secret. Projects using asymmetric JWT signing keys verify via JWKS.
    supabase_jwt_secret: str = ""

    # Server-only secret. Used for ingestion writes (lecture/job/media records,
    # storage uploads) after the API has verified ownership, and by the worker.
    # Never exposed to the frontend.
    supabase_service_role_key: str = ""

    # Direct database connection (reserved; unused so far)
    database_url: str = ""

    # Processing queue + worker
    redis_url: str = "redis://localhost:6379/0"
    queue_name: str = "lecturemind:processing"
    worker_lease_seconds: int = 120
    worker_heartbeat_seconds: int = 30
    worker_recovery_interval_seconds: int = 15
    worker_retry_backoff_seconds: int = 30
    # Per-job scratch space for downloads and FFmpeg output (never permanent storage).
    work_dir: str = ""
    ffmpeg_path: str = "ffmpeg"
    ffprobe_path: str = "ffprobe"
    ffmpeg_timeout_seconds: int = 1800

    # Ingestion limits (authoritative; the frontend reads them from the API)
    max_video_bytes: int = 2 * 1024**3
    max_audio_bytes: int = 500 * 1024**2
    max_media_duration_seconds: int = 4 * 3600
    source_url_downloads_enabled: bool = True

    # LLM provider (reserved for Phase 6 RAG; unused so far)
    llm_provider: str = ""
    llm_api_key: str = ""

    @field_validator("redis_url", mode="after")
    @classmethod
    def _redis_default(cls, value: str) -> str:
        # An empty REDIS_URL= line (older .env templates) means "use the local default".
        return value or "redis://localhost:6379/0"

    @property
    def cors_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_allow_origins.split(",") if origin.strip()]

    @property
    def is_development(self) -> bool:
        return self.environment == "development"

    @property
    def supabase_configured(self) -> bool:
        return bool(self.supabase_url and self.supabase_anon_key)

    @property
    def supabase_auth_issuer(self) -> str:
        return f"{self.supabase_url.rstrip('/')}/auth/v1"

    @property
    def supabase_rest_url(self) -> str:
        return f"{self.supabase_url.rstrip('/')}/rest/v1"

    @property
    def supabase_storage_url(self) -> str:
        return f"{self.supabase_url.rstrip('/')}/storage/v1"

    @property
    def ingestion_configured(self) -> bool:
        return self.supabase_configured and bool(self.supabase_service_role_key)

    @property
    def work_path(self) -> Path:
        return Path(self.work_dir) if self.work_dir else Path(tempfile.gettempdir()) / "lecturemind-work"


@lru_cache
def get_settings() -> Settings:
    return Settings()
