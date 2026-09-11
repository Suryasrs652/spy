"""JWT issuance and third-party refresh-token encryption.

§106: third-party OAuth refresh tokens (Google GSC) are encrypted at rest
using Fernet, keyed by TOKEN_ENCRYPTION_KEY — a key kept separate from the
database and rotatable independently of it.

Password hashing used to live here too; it went away with sign-in (Spy is
self-hosted and single-user now). The JWT helpers stay because the GSC
OAuth flow signs its `state` parameter with them.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Literal

import jwt
from cryptography.fernet import Fernet

from app.core.config import get_settings

TokenType = Literal["gsc_oauth_state"]


def issue_jwt(
    *,
    subject: str,
    token_type: TokenType,
    ttl: timedelta,
    extra_claims: dict[str, Any] | None = None,
) -> str:
    settings = get_settings()
    now = datetime.now(timezone.utc)
    payload: dict[str, Any] = {
        "sub": subject,
        "type": token_type,
        "iat": now,
        "exp": now + ttl,
        "jti": str(uuid.uuid4()),
    }
    if extra_claims:
        payload.update(extra_claims)
    return jwt.encode(payload, settings.auth_secret, algorithm=settings.jwt_algorithm)


def decode_jwt(token: str, *, expected_type: TokenType | None = None) -> dict[str, Any]:
    settings = get_settings()
    payload = jwt.decode(token, settings.auth_secret, algorithms=[settings.jwt_algorithm])
    if expected_type and payload.get("type") != expected_type:
        raise jwt.InvalidTokenError(f"expected token type {expected_type!r}")
    return payload


def _fernet() -> Fernet:
    return Fernet(get_settings().token_encryption_key.encode())


def encrypt_secret(plaintext: str) -> str:
    return _fernet().encrypt(plaintext.encode()).decode()


def decrypt_secret(ciphertext: str) -> str:
    return _fernet().decrypt(ciphertext.encode()).decode()
