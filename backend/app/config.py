"""
Central configuration for LectureMind backend.
All values are read from environment variables (see .env.example).
"""
import os
from pathlib import Path
from pydantic_settings import BaseSettings
from pydantic import Field

BASE_DIR = Path(__file__).resolve().parent.parent  # backend/
PROJECT_ROOT = BASE_DIR.parent  # LectureMind/


class Settings(BaseSettings):
    # --- General ---
    APP_NAME: str = "LectureMind"
    ENV: str = Field(default="development", env="ENV")
    CORS_ORIGINS: str = Field(default="http://localhost:5173,http://127.0.0.1:5173", env="CORS_ORIGINS")

    # --- Authentication ---
    SECRET_KEY: str = Field(default="change-me-in-production-use-a-long-random-string", env="SECRET_KEY")
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = Field(default=1440, env="ACCESS_TOKEN_EXPIRE_MINUTES")  # 24h

    # --- OTP ---
    OTP_LENGTH: int = Field(default=6, env="OTP_LENGTH")
    OTP_EXPIRE_MINUTES: int = Field(default=10, env="OTP_EXPIRE_MINUTES")
    OTP_MAX_ATTEMPTS: int = Field(default=5, env="OTP_MAX_ATTEMPTS")
    OTP_RESEND_COOLDOWN_SECONDS: int = Field(default=60, env="OTP_RESEND_COOLDOWN_SECONDS")

    # --- Email / SMS provider (abstraction) ---
    EMAIL_PROVIDER: str = Field(default="console", env="EMAIL_PROVIDER")  # console | smtp | sendgrid
    EMAIL_API_KEY: str = Field(default="", env="EMAIL_API_KEY")
    EMAIL_FROM: str = Field(default="noreply@lecturemind.app", env="EMAIL_FROM")
    SMTP_HOST: str = Field(default="", env="SMTP_HOST")
    SMTP_PORT: int = Field(default=587, env="SMTP_PORT")
    SMTP_USER: str = Field(default="", env="SMTP_USER")
    SMTP_PASSWORD: str = Field(default="", env="SMTP_PASSWORD")

    SMS_PROVIDER: str = Field(default="console", env="SMS_PROVIDER")  # console | twilio
    SMS_API_KEY: str = Field(default="", env="SMS_API_KEY")
    SMS_API_SECRET: str = Field(default="", env="SMS_API_SECRET")
    SMS_FROM: str = Field(default="", env="SMS_FROM")

    # --- Storage paths ---
    DATA_DIR: str = str(PROJECT_ROOT / "backend" / "data")
    UPLOAD_DIR: str = str(PROJECT_ROOT / "backend" / "data" / "uploads")
    AUDIO_DIR: str = str(PROJECT_ROOT / "backend" / "data" / "audio")
    TRANSCRIPT_DIR: str = str(PROJECT_ROOT / "backend" / "data" / "transcripts")
    SUMMARY_DIR: str = str(PROJECT_ROOT / "backend" / "data" / "summaries")
    CHROMA_DIR: str = str(PROJECT_ROOT / "backend" / "data" / "chroma")
    METADATA_DIR: str = str(PROJECT_ROOT / "backend" / "data" / "metadata")
    DATABASE_URL: str = Field(default="sqlite:///./data/metadata/lecturemind.db", env="DATABASE_URL")

    # --- Upload validation ---
    MAX_UPLOAD_SIZE_MB: int = Field(default=500, env="MAX_UPLOAD_SIZE_MB")
    ALLOWED_VIDEO_EXT: tuple = (".mp4", ".mkv", ".mov", ".avi")
    ALLOWED_AUDIO_EXT: tuple = (".mp3", ".wav", ".m4a")

    # --- Whisper / ASR ---
    WHISPER_MODEL_SIZE: str = Field(default="base", env="WHISPER_MODEL_SIZE")
    WHISPER_DEVICE: str = Field(default="cpu", env="WHISPER_DEVICE")
    WHISPER_COMPUTE_TYPE: str = Field(default="int8", env="WHISPER_COMPUTE_TYPE")

    # --- Embeddings ---
    EMBEDDING_MODEL: str = Field(default="sentence-transformers/all-MiniLM-L6-v2", env="EMBEDDING_MODEL")

    # --- Chunking ---
    CHUNK_SIZE_WORDS: int = Field(default=650, env="CHUNK_SIZE_WORDS")
    CHUNK_OVERLAP_WORDS: int = Field(default=120, env="CHUNK_OVERLAP_WORDS")

    # --- Retrieval ---
    TOP_K: int = Field(default=5, env="TOP_K")

    # --- LLM provider ---
    LLM_PROVIDER: str = Field(default="ollama", env="LLM_PROVIDER")  # ollama | openai | groq
    OLLAMA_BASE_URL: str = Field(default="http://localhost:11434", env="OLLAMA_BASE_URL")
    OLLAMA_MODEL: str = Field(default="llama3.1:8b", env="OLLAMA_MODEL")

    OPENAI_API_KEY: str = Field(default="", env="OPENAI_API_KEY")
    OPENAI_MODEL: str = Field(default="gpt-4o-mini", env="OPENAI_MODEL")

    GROQ_API_KEY: str = Field(default="", env="GROQ_API_KEY")
    GROQ_MODEL: str = Field(default="openai/gpt-oss-20b", env="GROQ_MODEL")

    LLM_TIMEOUT_SECONDS: int = Field(default=120, env="LLM_TIMEOUT_SECONDS")

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"


settings = Settings()

# Ensure all storage directories exist at import time.
for _dir in [
    settings.DATA_DIR,
    settings.UPLOAD_DIR,
    settings.AUDIO_DIR,
    settings.TRANSCRIPT_DIR,
    settings.SUMMARY_DIR,
    settings.CHROMA_DIR,
    settings.METADATA_DIR,
]:
    os.makedirs(_dir, exist_ok=True)
