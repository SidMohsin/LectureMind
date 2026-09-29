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

    # Supabase (used by future auth/storage work, not Phase 1)
    supabase_url: str = ""
    supabase_service_key: str = ""

    # Database (used by future persistence work, not Phase 1)
    database_url: str = ""

    # Redis / queue (used by future processing work, not Phase 1)
    redis_url: str = ""

    # LLM provider (used by future RAG work, not Phase 1)
    llm_provider: str = ""
    llm_api_key: str = ""

    @property
    def cors_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_allow_origins.split(",") if origin.strip()]

    @property
    def is_development(self) -> bool:
        return self.environment == "development"


@lru_cache
def get_settings() -> Settings:
    return Settings()
