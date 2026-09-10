"""Guard for service-to-service endpoints (§15).

Only Next.js's own server-side code (never the browser) calls these routes,
authenticated with a shared secret that is never exposed to the client. The
BFF proxy in apps/web only forwards `/api/v1/*`; it never proxies `/internal/*`.
"""
from __future__ import annotations

import hmac

from fastapi import Header

from app.core.config import get_settings
from app.core.errors import UnauthenticatedError


async def require_internal_service_token(
    x_internal_token: str | None = Header(default=None, alias="X-Internal-Token"),
) -> None:
    settings = get_settings()
    # hmac.compare_digest, not `!=` — a naive equality check short-circuits
    # on the first mismatched byte, letting a network-position attacker
    # recover the token one byte at a time via response-time measurements.
    if not x_internal_token or not hmac.compare_digest(x_internal_token, settings.internal_service_token):
        raise UnauthenticatedError("Invalid internal service token.")
