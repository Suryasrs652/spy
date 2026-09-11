"""§104 security hardening pass.

The login brute-force and internal-token tests went away with sign-in
itself (Spy is self-hosted and single-user now). What's left still
applies to any deployment: an unconditionally trusted X-Forwarded-For
(rate-limit bypass) and unchecked default secrets reaching a production
boot.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.core.config import Settings, get_settings
from app.core.ratelimit import client_ip


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
            token_encryption_key="a-real-fernet-key-not-the-shipped-default==",
        )


def test_production_settings_accept_real_secrets() -> None:
    settings = Settings(
        environment="production",
        auth_secret="a-real-random-secret-value",
        token_encryption_key="a-real-fernet-key-not-the-shipped-default==",
    )
    assert settings.is_production


def test_development_settings_allow_placeholder_defaults() -> None:
    # The whole point of the check is that it only bites in production —
    # local dev must keep working with the documented placeholder values.
    Settings(environment="development")
