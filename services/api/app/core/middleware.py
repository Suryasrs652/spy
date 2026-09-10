"""Request-id + structured access logging middleware (§110), plus §104
security response headers.
"""
from __future__ import annotations

import time
import uuid

import structlog
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

logger = structlog.get_logger(__name__)

# §104 — every response from this API is JSON, never HTML, so there is no
# legitimate reason a browser should ever render, frame, or execute one:
# CSP default-src 'none' neuters a response even in the (should-never-
# happen) case a client mistakes it for HTML; the rest are standard
# defense-in-depth headers with no downside for a pure JSON API.
_SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Content-Security-Policy": "default-src 'none'; frame-ancestors 'none'",
    "Permissions-Policy": "geolocation=(), camera=(), microphone=()",
    # Harmless to send over plain HTTP (browsers only honor it on HTTPS
    # responses) and required once this sits behind TLS in production.
    "Strict-Transport-Security": "max-age=63072000; includeSubDomains",
}


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        response = await call_next(request)
        for header, value in _SECURITY_HEADERS.items():
            response.headers.setdefault(header, value)
        return response


class RequestContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        request_id = request.headers.get("X-Request-Id") or str(uuid.uuid4())
        request.state.request_id = request_id

        start = time.perf_counter()
        response = await call_next(request)
        duration_ms = round((time.perf_counter() - start) * 1000, 2)

        response.headers["X-Request-Id"] = request_id

        logger.info(
            "request",
            request_id=request_id,
            method=request.method,
            route=request.url.path,
            status=response.status_code,
            duration_ms=duration_ms,
        )
        return response
