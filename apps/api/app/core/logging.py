"""structlog JSON logging configuration.

Binds request_id / tenant_id into the log context and redacts sensitive keys
(`token`, `email`, `authorization`, secrets) so PII and credentials never reach
the logs (blueprint §11, §13.3).
"""

from __future__ import annotations

import logging

import structlog

_REDACT_KEYS = {
    "token",
    "access_token",
    "authorization",
    "password",
    "client_secret",
    "gemini_api_key",
    "email",
}


def _redact(_logger, _method, event_dict):
    for key in list(event_dict.keys()):
        if key.lower() in _REDACT_KEYS:
            event_dict[key] = "[redacted]"
    return event_dict


def configure_logging(level: str = "INFO") -> None:
    logging.basicConfig(format="%(message)s", level=level.upper())
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            _redact,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(logging.getLevelName(level.upper())),
        cache_logger_on_first_use=True,
    )
