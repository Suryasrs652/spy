"""§104 security hardening pass — each test targets one concrete gap found
during the audit: an unrated login endpoint (online brute force), a
naive `!=` secret comparison (timing side-channel), an unconditionally
trusted X-Forwarded-For (rate-limit bypass), and unchecked default secrets
reaching a production boot.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.core.config import Settings, get_settings
from app.core.ratelimit import client_ip
from tests.conftest import unique_email


def _make_request(*, client_host: str, xff: str | None):
    headers = {"X-Forwarded-For": xff} if xff else {}
    return SimpleNamespace(headers=headers, client=SimpleNamespace(host=client_host))


def test_client_ip_ignores_forwarded_header_by_default(monkeypatch) -> None:
    settings = get_settings()
    monkeypatch.setattr(settings, "trust_proxy_headers", False)
    request = _make_request(client_host="203.0.113.9", xff="1.2.3.4")
    assert client_ip(request) == "203.0.113.9", (
        "an unspoofable socket peer must win over a client-suppliable header unless "
        "TRUST_PROXY_HEADERS is explicitly turned on"
    )


def test_client_ip_honors_forwarded_header_when_trusted(monkeypatch) -> None:
    settings = get_settings()
    monkeypatch.setattr(settings, "trust_proxy_headers", True)
    request = _make_request(client_host="203.0.113.9", xff="1.2.3.4, 203.0.113.9")
    assert client_ip(request) == "1.2.3.4"


def test_production_settings_reject_default_auth_secret() -> None:
    # auth_secret is passed explicitly (as the literal shipped placeholder)
    # rather than left to fall through to whatever this environment's real
    # .env/OS env vars happen to hold — explicit constructor kwargs
    # outrank both in pydantic-settings' source priority, so this is the
    # only way to deterministically exercise "still the placeholder"
    # regardless of what's actually configured for this test run.
    with pytest.raises(ValueError, match="auth_secret"):
        Settings(
            environment="production",
            auth_secret="insecure-dev-secret-change-me",
            internal_service_token="a-real-token-value",
            token_encryption_key="a-real-fernet-key-not-the-shipped-default==",
        )


def test_production_settings_accept_real_secrets() -> None:
    settings = Settings(
        environment="production",
        auth_secret="a-real-random-secret-value",
        internal_service_token="a-real-token-value",
        token_encryption_key="a-real-fernet-key-not-the-shipped-default==",
    )
    assert settings.is_production


def test_development_settings_allow_placeholder_defaults() -> None:
    # The whole point of the check is that it only bites in production —
    # local dev must keep working with the documented placeholder values.
    Settings(environment="development")


@pytest.mark.asyncio
async def test_login_attempts_are_rate_limited_per_email(client) -> None:
    from app.core.config import get_settings as _get_settings
    from app.modules.auth import service as auth_service

    settings = _get_settings()
    email = unique_email()

    from app.db.session import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        await auth_service.signup(db, email=email, password="correct horse battery staple", name=None)

    headers = {"X-Internal-Token": settings.internal_service_token}
    responses = []
    for _ in range(12):
        resp = await client.post(
            "/internal/auth/verify-credentials",
            json={"email": email, "password": "definitely-the-wrong-password"},
            headers=headers,
        )
        responses.append(resp.status_code)

    assert all(s == 401 for s in responses[:10]), "wrong-password attempts within budget should read as 401"
    assert 429 in responses[10:], "attempts past the per-email budget must be rate-limited, not silently allowed"


@pytest.mark.asyncio
async def test_internal_token_endpoint_rejects_wrong_token(client) -> None:
    resp = await client.post(
        "/internal/auth/verify-credentials",
        json={"email": unique_email(), "password": "whatever"},
        headers={"X-Internal-Token": "not-the-real-token"},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_internal_token_endpoint_rejects_missing_token(client) -> None:
    resp = await client.post(
        "/internal/auth/verify-credentials",
        json={"email": unique_email(), "password": "whatever"},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_password_hash_and_verify_roundtrip() -> None:
    """§104 load-test finding: hash_password/verify_password moved onto
    asyncio.to_thread so Argon2id's CPU-bound work stops blocking the
    event loop — this locks in that the roundtrip is still correct.
    """
    from app.core.security import hash_password, verify_password

    hashed = await hash_password("correct horse battery staple")
    assert await verify_password("correct horse battery staple", hashed) is True
    assert await verify_password("wrong password", hashed) is False
