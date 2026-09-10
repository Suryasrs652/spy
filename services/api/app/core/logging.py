"""Structured JSON logging (§110) with secret redaction.

Never logs: password, OAuth refresh/access tokens, payment secrets,
Authorization headers. The redaction processor below scrubs any key whose
name matches a sensitive pattern, recursively, before a log line is emitted.
"""
from __future__ import annotations

import logging
import re
import sys
from typing import Any

import structlog

_SENSITIVE_KEY_RE = re.compile(
    r"(password|secret|token|authorization|api_key|refresh_token|access_token|signature)",
    re.IGNORECASE,
)


def _redact(_logger: Any, _method_name: str, event_dict: dict[str, Any]) -> dict[str, Any]:
    def scrub(value: Any) -> Any:
        if isinstance(value, dict):
            return {
                k: ("***REDACTED***" if _SENSITIVE_KEY_RE.search(str(k)) else scrub(v))
                for k, v in value.items()
            }
        if isinstance(value, list):
            return [scrub(v) for v in value]
        return value

    return {
        k: ("***REDACTED***" if _SENSITIVE_KEY_RE.search(str(k)) else scrub(v))
        for k, v in event_dict.items()
    }


def configure_logging(*, json_logs: bool = True) -> None:
    logging.basicConfig(format="%(message)s", stream=sys.stdout, level=logging.INFO)

    shared_processors: list[Any] = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        _redact,
    ]

    structlog.configure(
        processors=shared_processors
        + [
            structlog.processors.JSONRenderer()
            if json_logs
            else structlog.dev.ConsoleRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )
