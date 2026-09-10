"""§31 Google Search Console OAuth connect flow.

Scope is minimal per §31: `webmasters.readonly`. Calls here go to Google's
own well-known API hosts (accounts.google.com, oauth2.googleapis.com,
www.googleapis.com) — trusted first-party endpoints, not user-supplied
URLs — so they use a plain httpx client rather than the SSRF-guarded
`SafeFetcher` (§107's guard is specifically for arbitrary, user-controlled
crawl targets).

Data sync (§32-§34) is M2; this module only gets the connection established
and verified properties listed, gated behind the `GSC_ENABLED` feature flag.
"""
from __future__ import annotations

import uuid
from datetime import timedelta
from urllib.parse import urlencode

import httpx
import jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.errors import ValidationAppError
from app.core.security import decrypt_secret, encrypt_secret, issue_jwt, decode_jwt
from app.db.base import utcnow
from app.modules.gsc.models import GscConnection, GscConnectionStatus, GscProperty

GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_SITES_URL = "https://www.googleapis.com/webmasters/v3/sites"
GSC_SCOPE = "https://www.googleapis.com/auth/webmasters.readonly"


def build_authorization_url(*, organization_id: uuid.UUID, user_id: uuid.UUID) -> str:
    settings = get_settings()
    state = issue_jwt(
        subject=str(user_id), token_type="gsc_oauth_state",
        ttl=timedelta(minutes=10), extra_claims={"organization_id": str(organization_id)},
    )
    params = {
        "client_id": settings.google_client_id,
        "redirect_uri": settings.google_gsc_redirect_uri,
        "response_type": "code",
        "scope": GSC_SCOPE,
        "access_type": "offline",
        "prompt": "consent",
        "state": state,
    }
    return f"{GOOGLE_AUTH_URL}?{urlencode(params)}"


def decode_state(state: str) -> tuple[uuid.UUID, uuid.UUID]:
    try:
        payload = decode_jwt(state, expected_type="gsc_oauth_state")
    except jwt.InvalidTokenError as exc:
        raise ValidationAppError("Invalid or expired OAuth state.") from exc
    return uuid.UUID(payload["organization_id"]), uuid.UUID(payload["sub"])


async def exchange_code_for_tokens(code: str) -> dict:
    settings = get_settings()
    async with httpx.AsyncClient(timeout=15.0) as client:
        response = await client.post(
            GOOGLE_TOKEN_URL,
            data={
                "code": code,
                "client_id": settings.google_client_id,
                "client_secret": settings.google_client_secret,
                "redirect_uri": settings.google_gsc_redirect_uri,
                "grant_type": "authorization_code",
            },
        )
    if response.status_code != 200:
        raise ValidationAppError("Failed to exchange authorization code with Google.")
    return response.json()


async def fetch_verified_sites(access_token: str) -> list[dict]:
    async with httpx.AsyncClient(timeout=15.0) as client:
        response = await client.get(GOOGLE_SITES_URL, headers={"Authorization": f"Bearer {access_token}"})
    if response.status_code != 200:
        return []
    return response.json().get("siteEntry", [])


async def complete_connection(
    db: AsyncSession, *, organization_id: uuid.UUID, user_id: uuid.UUID, code: str
) -> GscConnection:
    tokens = await exchange_code_for_tokens(code)
    refresh_token = tokens.get("refresh_token")
    access_token = tokens.get("access_token")
    if not refresh_token:
        # Google omits refresh_token on repeat consent without prompt=consent;
        # we always pass prompt=consent, but guard anyway.
        raise ValidationAppError(
            "Google did not return a refresh token. Please disconnect and reconnect to grant offline access."
        )

    # Google account id isn't directly in the token response; derive a
    # stable identifier from the id_token if present, else fall back to a
    # per-connection UUID (still unique per row, just not cross-referenced
    # to the same Google account across reconnects).
    google_account_id = tokens.get("id_token", "")[:64] or str(uuid.uuid4())

    existing = (
        await db.execute(
            select(GscConnection).where(GscConnection.organization_id == organization_id)
        )
    ).scalar_one_or_none()

    if existing is not None:
        existing.encrypted_refresh_token = encrypt_secret(refresh_token)
        existing.status = GscConnectionStatus.ACTIVE.value
        existing.connected_at = utcnow()
        connection = existing
    else:
        connection = GscConnection(
            organization_id=organization_id,
            user_id=user_id,
            google_account_id=google_account_id,
            encrypted_refresh_token=encrypt_secret(refresh_token),
            scopes=[GSC_SCOPE],
            status=GscConnectionStatus.ACTIVE.value,
        )
        db.add(connection)
    await db.flush()

    if access_token:
        sites = await fetch_verified_sites(access_token)
        for site in sites:
            site_url = site.get("siteUrl")
            if not site_url:
                continue
            existing_prop = (
                await db.execute(
                    select(GscProperty).where(
                        GscProperty.connection_id == connection.id, GscProperty.site_url == site_url
                    )
                )
            ).scalar_one_or_none()
            if existing_prop is None:
                db.add(
                    GscProperty(
                        connection_id=connection.id, site_url=site_url,
                        permission_level=site.get("permissionLevel", "unknown"),
                    )
                )

    await db.commit()
    await db.refresh(connection)
    return connection


async def list_properties(db: AsyncSession, *, organization_id: uuid.UUID) -> list[GscProperty]:
    connection = (
        await db.execute(select(GscConnection).where(GscConnection.organization_id == organization_id))
    ).scalar_one_or_none()
    if connection is None:
        return []
    result = await db.execute(select(GscProperty).where(GscProperty.connection_id == connection.id))
    return list(result.scalars().all())


def _decrypt_refresh_token(connection: GscConnection) -> str:
    return decrypt_secret(connection.encrypted_refresh_token)
