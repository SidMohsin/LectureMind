"""Shared error response conventions for the API.

Every error response follows the same JSON shape so the frontend can rely on
a single parsing path regardless of which endpoint failed.
"""

import json
import logging

from fastapi import FastAPI, Request, status
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger(__name__)


class UpstreamServiceError(Exception):
    """A dependency (e.g. Supabase) failed or returned an unexpected error."""


class AppError(Exception):
    """An expected, user-facing failure with a stable machine-readable code."""

    def __init__(
        self, status_code: int, code: str, message: str, details: object | None = None, headers: dict[str, str] | None = None
    ):
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.details = details
        self.headers = headers


def upstream_error_summary(body: str | bytes, limit: int = 200) -> str:
    """A loggable summary of an upstream (Supabase) error body.

    PostgREST error bodies put the offending row in "details" (e.g. "Failing row contains
    (...)"), which can include private lecture or question text. Only the machine fields
    (code, message, hint, error) are kept; anything that isn't JSON is reduced to its size.
    """
    if isinstance(body, bytes):
        body = body.decode("utf-8", errors="replace")
    try:
        data = json.loads(body)
    except (ValueError, TypeError):
        return f"<non-json body, {len(body or '')} chars>"
    if not isinstance(data, dict):
        return "<unexpected body>"
    parts = [f"{key}={str(data[key])[:limit]}" for key in ("code", "error", "message", "hint", "statusCode") if data.get(key)]
    return " ".join(parts) or "<no error fields>"


def error_body(message: str, *, code: str | None = None, details: object | None = None) -> dict:
    return {
        "message": message,
        "code": code,
        "details": details,
    }


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(request: Request, exc: StarletteHTTPException):
        return JSONResponse(
            status_code=exc.status_code,
            content=error_body(str(exc.detail), code="http_error"),
            headers=getattr(exc, "headers", None),
        )

    @app.exception_handler(AppError)
    async def app_error_handler(request: Request, exc: AppError):
        return JSONResponse(
            status_code=exc.status_code,
            content=error_body(exc.message, code=exc.code, details=exc.details),
            headers=exc.headers,
        )

    @app.exception_handler(UpstreamServiceError)
    async def upstream_exception_handler(request: Request, exc: UpstreamServiceError):
        return JSONResponse(
            status_code=status.HTTP_502_BAD_GATEWAY,
            content=error_body("A required service is temporarily unavailable. Please try again.", code="upstream_error"),
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError):
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            content=error_body("Request validation failed.", code="validation_error", details=jsonable_encoder(exc.errors(), custom_encoder={Exception: str})),
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception):
        # The path only: query strings can carry user content (e.g. search text).
        logger.exception("unhandled_error method=%s path=%s", request.method, request.url.path)
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=error_body("An unexpected error occurred.", code="internal_error"),
        )
