"""Redis-backed fixed-window rate limiter (§100).

Applied to login, signup, password reset, audit creation, keyword lookup,
PDF export, GSC sync and other public/sensitive endpoints. Keyed by IP,
user, and/or organization depending on the endpoint — callers choose which
key(s) apply via `key_parts`.
"""
from __future__ import annotations

from fastapi import Request

from app.core.config import get_settings
from app.core.errors import RateLimitedError
from app.db.redis import get_redis


def _bucket_key(scope: str, key: str, window_seconds: int) -> str:
    import time

    window = int(time.time() // window_seconds)
    return f"ratelimit:{scope}:{key}:{window}"


async def enforce_rate_limit(
    *, scope: str, key: str, limit: int, window_seconds: int = 60
) -> None:
    redis = get_redis()
    bucket = _bucket_key(scope, key, window_seconds)
    count = await redis.incr(bucket)
    if count == 1:
        await redis.expire(bucket, window_seconds)
    if count > limit:
        raise RateLimitedError(
            f"Too many requests for {scope!r}. Try again shortly."
        )


def client_ip(request: Request) -> str:
    # §104 — X-Forwarded-For is only trustworthy when a proxy in front of
    # this process sets it itself (and strips any client-supplied value
    # first); otherwise any caller can put an arbitrary IP in it and get a
    # fresh rate-limit bucket on every request. TRUST_PROXY_HEADERS is off
    # by default (app/core/config.py) so the raw socket peer — which a
    # request can never spoof — is what gets used unless a real deployment
    # explicitly vouches for its proxy.
    if get_settings().trust_proxy_headers:
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def rate_limit_dependency(scope: str, limit: int, window_seconds: int = 60):
    """FastAPI dependency factory: rate-limits by client IP.

    Use `enforce_rate_limit` directly inside a route when you need to key by
    user/org instead of (or in addition to) IP.
    """

    async def _dep(request: Request) -> None:
        await enforce_rate_limit(
            scope=scope, key=client_ip(request), limit=limit, window_seconds=window_seconds
        )

    return _dep
