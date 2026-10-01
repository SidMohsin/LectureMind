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

    # --- Lecture intelligence (Phase 5) ---
    # Where downloaded speech/embedding models are cached (outside the repo).
    model_cache_dir: str = ""
    # faster-whisper (CTranslate2): model size/name, device and precision.
    transcription_model: str = "small"
    transcription_device: str = "cpu"
    transcription_compute_type: str = "int8"
    transcription_beam_size: int = 5
    # Empty = detect the spoken language.
    transcription_language: str = ""
    # fastembed (ONNX) sentence-embedding model and its output dimension.
    embedding_model: str = "BAAI/bge-small-en-v1.5"
    embedding_dimension: int = 384
    # Chunking targets, in estimated tokens.
    chunk_min_tokens: int = 200
    chunk_max_tokens: int = 400
    chunk_overlap_tokens: int = 50
    # OpenAI-compatible chat completions API (OpenAI, Groq, Gemini's OpenAI
    # endpoint, a local Ollama server, ...).
    llm_base_url: str = ""
    llm_api_key: str = ""
    llm_model: str = ""
    llm_temperature: float = 0.2
    llm_timeout_seconds: int = 180
    # Transcript text per LLM request; longer lectures are summarised in ordered parts.
    llm_window_tokens: int = 12000
    # Upper bound on each response. Some providers count it against per-minute limits.
    llm_max_output_tokens: int = 4000
    # How often to wait-and-retry a single request the provider rate-limits (HTTP 429).
    llm_rate_limit_retries: int = 6
    # For reasoning models (e.g. gpt-oss, o-series): "low" | "medium" | "high". Empty = not sent.
    llm_reasoning_effort: str = ""

    # --- Lecture workspace + grounded Q&A (Phase 6) ---
    # Private playback audio stored for lectures whose source isn't an upload (e.g. YouTube).
    # The bitrate is lowered (not below the minimum) so the file fits playback_max_bytes,
    # which must not exceed the storage plan's per-file limit (50 MB on Supabase Free).
    playback_audio_bitrate_kbps: int = 48
    playback_min_bitrate_kbps: int = 24
    playback_max_bytes: int = 48 * 1024**2
    # How long a signed media URL handed to the player stays valid.
    media_url_ttl_seconds: int = 3600
    # Retrieval: candidates fetched per question, and the minimum cosine similarity a
    # chunk needs to count as evidence (calibrated for bge-small-en-v1.5; see README).
    rag_top_k: int = 6
    rag_min_similarity: float = 0.6
    # Evidence passed to the LLM per question (estimated tokens) and its answer cap.
    rag_context_tokens: int = 2400
    rag_max_output_tokens: int = 900
    # Interactive requests shouldn't sit out long provider rate limits.
    rag_rate_limit_retries: int = 1

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
    def model_cache_path(self) -> Path:
        return Path(self.model_cache_dir) if self.model_cache_dir else Path.home() / ".cache" / "lecturemind-models"

    @property
    def llm_configured(self) -> bool:
        return bool(self.llm_base_url and self.llm_model)

    @property
    def work_path(self) -> Path:
        return Path(self.work_dir) if self.work_dir else Path(tempfile.gettempdir()) / "lecturemind-work"


@lru_cache
def get_settings() -> Settings:
    return Settings()
