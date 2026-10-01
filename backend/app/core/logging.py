"""Structured logging setup for the API and the worker.

Every line carries a correlation id (the request id in the API, the job id in the
worker). LOG_FORMAT=json emits one JSON object per line for log collectors.

Third-party loggers that would print full request URLs are kept at WARNING: Supabase
request URLs carry filters built from user input (e.g. search text), and uvicorn's
access log includes query strings. Request lines are logged by
app.core.observability instead, without query strings, headers or bodies.
"""

import logging
import sys

from app.core.config import get_settings
from app.core.observability import CorrelationFilter, JsonFormatter

TEXT_FORMAT = "%(asctime)s | %(levelname)s | %(name)s | %(correlation_id)s | %(message)s"
QUIET_LOGGERS = ("httpx", "httpcore", "uvicorn.access", "hpack", "faster_whisper")


def configure_logging() -> None:
    settings = get_settings()

    handler = logging.StreamHandler(sys.stdout)
    handler.addFilter(CorrelationFilter())
    if settings.log_format.lower() == "json":
        handler.setFormatter(JsonFormatter())
    else:
        handler.setFormatter(logging.Formatter(fmt=TEXT_FORMAT, datefmt="%Y-%m-%dT%H:%M:%S"))

    root_logger = logging.getLogger()
    root_logger.handlers = [handler]
    root_logger.setLevel(settings.log_level.upper())
    for name in QUIET_LOGGERS:
        logging.getLogger(name).setLevel(max(logging.WARNING, root_logger.level))
