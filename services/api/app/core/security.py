"""Password hashing, JWT issuance, and refresh-token encryption.

§105: passwords use Argon2id, never MD5/SHA1/plain SHA256.
§106: third-party OAuth refresh tokens (Google GSC) are encrypted at rest
using Fernet, keyed by TOKEN_ENCRYPTION_KEY — a key kept separate from the
database and rotatable independently of it.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Literal

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from cryptography.fernet import Fernet

from app.core.config import get_settings

_hasher = PasswordHasher()

# A structurally-valid Argon2id hash of a value nobody will ever type, used
# to keep the "user not found" and "wrong password" code paths doing the
# same amount of work — verifying against a real hash rather than skipping
# straight to failure avoids a timing signal that would leak account
# existence during login.
DUMMY_PASSWORD_HASH = _hasher.hash("spy-dummy-password-for-constant-time-login-checks")


def hash_password(plain: str) -> str:
    return _hasher.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return _hasher.verify(hashed, plain)
    except VerifyMismatchError:
        return False
    except Exception:  # noqa: BLE001 - malformed hash, tampering, etc.
        return False


TokenType = Literal["access", "refresh", "email_verify", "password_reset", "gsc_oauth_state"]


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


def issue_access_token(user_id: str, org_id: str | None = None) -> str:
    settings = get_settings()
    claims = {"org_id": org_id} if org_id else {}
    return issue_jwt(
        subject=user_id,
        token_type="access",
        ttl=timedelta(minutes=settings.access_token_ttl_minutes),
        extra_claims=claims,
    )


def issue_refresh_token(user_id: str) -> str:
    settings = get_settings()
    return issue_jwt(
        subject=user_id,
        token_type="refresh",
        ttl=timedelta(days=settings.refresh_token_ttl_days),
    )


def _fernet() -> Fernet:
    return Fernet(get_settings().token_encryption_key.encode())


def encrypt_secret(plaintext: str) -> str:
    return _fernet().encrypt(plaintext.encode()).decode()


def decrypt_secret(ciphertext: str) -> str:
    return _fernet().decrypt(ciphertext.encode()).decode()
