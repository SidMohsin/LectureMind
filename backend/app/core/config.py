"""Centralized application configuration.

All configuration is loaded from environment variables (see .env.example).
Nothing here should be hard-coded per environment; environment separation is
achieved by pointing each deployment at its own .env / process environment.
"""

from functools import lru_cache

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

    # Direct database connection (reserved for workers in later phases; unused so far)
    database_url: str = ""

    # Redis / queue (reserved for Phase 4 processing; unused so far)
    redis_url: str = ""

    # LLM provider (reserved for Phase 6 RAG; unused so far)
    llm_provider: str = ""
    llm_api_key: str = ""

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


@lru_cache
def get_settings() -> Settings:
    return Settings()
