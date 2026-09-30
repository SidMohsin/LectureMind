"""Shared error response conventions for the API.

Every error response follows the same JSON shape so the frontend can rely on
a single parsing path regardless of which endpoint failed.
"""

import logging

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger(__name__)


class UpstreamServiceError(Exception):
    """A dependency (e.g. Supabase) failed or returned an unexpected error."""


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
            content=error_body("Request validation failed.", code="validation_error", details=exc.errors()),
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception):
        logger.exception("Unhandled error while processing %s %s", request.method, request.url.path)
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=error_body("An unexpected error occurred.", code="internal_error"),
        )
