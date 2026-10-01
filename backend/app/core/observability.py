"""Request correlation, security headers and structured request logging.

Every request gets a correlation id (a well-formed incoming X-Request-ID is reused,
otherwise a new one is generated). It is returned in the X-Request-ID header and
attached to every log line written while the request is handled, so API logs,
upstream errors and timing lines can be joined. The worker uses the same field
for the job id.

Logged request lines contain the method, the route template (not the raw URL, so
query strings with search text never reach the logs), status and duration. They
never contain headers, tokens or bodies.
"""

import contextvars
import json
import logging
import re
import time
import uuid

correlation_id: contextvars.ContextVar[str] = contextvars.ContextVar("correlation_id", default="-")

logger = logging.getLogger("app.requests")

_VALID_ID = re.compile(r"^[A-Za-z0-9._-]{8,64}$")
_DOCS_PATHS = ("/docs", "/redoc", "/openapi.json")
_QUIET_PATHS = ("/health",)


class CorrelationFilter(logging.Filter):
    """Adds `correlation_id` to every record (logging must never fail for want of it)."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.correlation_id = correlation_id.get()
        return True


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        entry = {
            "time": self.formatTime(record, "%Y-%m-%dT%H:%M:%S"),
            "level": record.levelname,
            "logger": record.name,
            "correlation_id": getattr(record, "correlation_id", "-"),
            "message": record.getMessage(),
        }
        if record.exc_info:
            entry["exception"] = self.formatException(record.exc_info)
        return json.dumps(entry, ensure_ascii=False)


def security_headers(path: str, *, hsts: bool) -> list[tuple[bytes, bytes]]:
    headers = [
        (b"x-content-type-options", b"nosniff"),
        (b"x-frame-options", b"DENY"),
        (b"referrer-policy", b"no-referrer"),
        (b"cross-origin-opener-policy", b"same-origin"),
        (b"permissions-policy", b"camera=(), microphone=(), geolocation=(), payment=()"),
    ]
    if not path.startswith(_DOCS_PATHS):
        # The API only returns JSON: nothing may be loaded or framed from its responses,
        # and responses (which carry private lecture data) must not be cached.
        headers.append((b"content-security-policy", b"default-src 'none'; frame-ancestors 'none'"))
        headers.append((b"cache-control", b"no-store"))
    if hsts:
        headers.append((b"strict-transport-security", b"max-age=31536000; includeSubDomains"))
    return headers


class RequestContextMiddleware:
    """Pure ASGI middleware (streams request bodies untouched, e.g. large uploads)."""

    def __init__(self, app, *, hsts: bool = False):
        self.app = app
        self.hsts = hsts

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        incoming = dict(scope.get("headers") or []).get(b"x-request-id", b"").decode("latin-1")
        request_id = incoming if _VALID_ID.match(incoming) else uuid.uuid4().hex
        token = correlation_id.set(request_id)
        started = time.monotonic()
        status_code = 500
        path = scope.get("path", "")

        async def send_with_headers(message):
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
                existing = {name.lower() for name, _ in message.get("headers", [])}
                extra = [(b"x-request-id", request_id.encode())] + [
                    header for header in security_headers(path, hsts=self.hsts) if header[0] not in existing
                ]
                message = {**message, "headers": list(message.get("headers", [])) + extra}
            await send(message)

        try:
            await self.app(scope, receive, send_with_headers)
        finally:
            route = scope.get("route")
            template = getattr(route, "path", None) or ("<unmatched>" if status_code == 404 else path)
            duration_ms = int((time.monotonic() - started) * 1000)
            level = logging.DEBUG if path in _QUIET_PATHS or scope.get("method") == "OPTIONS" else logging.INFO
            logger.log(
                level,
                "request method=%s route=%s status=%s duration_ms=%s",
                scope.get("method"),
                template,
                status_code,
                duration_ms,
            )
            correlation_id.reset(token)
