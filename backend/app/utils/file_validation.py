"""
File validation helpers: extension checks, size checks, safe filenames.
"""
import os
import re
import uuid
from fastapi import UploadFile
from app.config import settings


class FileValidationError(Exception):
    pass


def safe_filename(original_filename: str) -> str:
    """Generate a collision-safe, filesystem-safe filename while keeping the extension."""
    ext = os.path.splitext(original_filename)[1].lower()
    base = re.sub(r"[^a-zA-Z0-9_-]", "_", os.path.splitext(original_filename)[0])[:50]
    unique = uuid.uuid4().hex[:8]
    return f"{base}_{unique}{ext}"


def classify_extension(filename: str) -> str:
    ext = os.path.splitext(filename)[1].lower()
    if ext in settings.ALLOWED_VIDEO_EXT:
        return "video"
    if ext in settings.ALLOWED_AUDIO_EXT:
        return "audio"
    raise FileValidationError(
        f"Unsupported file type '{ext}'. Allowed video: {settings.ALLOWED_VIDEO_EXT}, "
        f"allowed audio: {settings.ALLOWED_AUDIO_EXT}"
    )


async def validate_upload(file: UploadFile) -> str:
    """Validates extension and size. Returns file_type ('video'|'audio'). Raises FileValidationError."""
    if not file.filename:
        raise FileValidationError("No filename provided.")

    file_type = classify_extension(file.filename)

    # Measure size by reading in chunks (UploadFile doesn't expose size reliably before read)
    max_bytes = settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024
    size = 0
    chunk_size = 1024 * 1024
    chunks = []
    while True:
        chunk = await file.read(chunk_size)
        if not chunk:
            break
        size += len(chunk)
        chunks.append(chunk)
        if size > max_bytes:
            raise FileValidationError(
                f"File exceeds maximum allowed size of {settings.MAX_UPLOAD_SIZE_MB} MB."
            )
    await file.seek(0)
    if size == 0:
        raise FileValidationError("Uploaded file is empty.")

    return file_type
