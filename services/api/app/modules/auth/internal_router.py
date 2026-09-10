"""Service-to-service auth endpoints.

Only apps/web's server-side Auth.js code calls these — never the browser —
authenticated with X-Internal-Token (§core.internal_auth). This is where
Argon2id verification and Google-identity upsert actually happen; Auth.js
never touches a password hash.
"""
from __future__ import annotations

import jwt
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import UnauthenticatedError
from app.core.internal_auth import require_internal_service_token
from app.core.security import decode_jwt, issue_access_token, issue_refresh_token
from app.db.session import get_db
from app.modules.auth import service
from app.modules.auth.schemas import (
    InternalUserOut,
    OAuthUpsertRequest,
    RefreshRequest,
    RefreshResponse,
    VerifyCredentialsRequest,
)

router = APIRouter(
    prefix="/internal/auth",
    tags=["internal"],
    dependencies=[Depends(require_internal_service_token)],
)


async def _issue_tokens(db: AsyncSession, user_id, email, email_verified) -> InternalUserOut:
    org_id = await service.default_organization_id(db, user_id)
    return InternalUserOut(
        user_id=user_id,
        email=email,
        email_verified=email_verified,
        default_organization_id=org_id,
        access_token=issue_access_token(str(user_id), str(org_id)),
        refresh_token=issue_refresh_token(str(user_id)),
    )


@router.post("/verify-credentials", response_model=InternalUserOut)
async def verify_credentials(
    payload: VerifyCredentialsRequest, db: AsyncSession = Depends(get_db)
) -> InternalUserOut:
    user = await service.verify_credentials(db, email=payload.email, password=payload.password)
    return await _issue_tokens(db, user.id, user.email, user.is_email_verified)


@router.post("/oauth-upsert", response_model=InternalUserOut)
async def oauth_upsert(payload: OAuthUpsertRequest, db: AsyncSession = Depends(get_db)) -> InternalUserOut:
    user = await service.oauth_upsert(
        db, email=payload.email, google_sub=payload.google_sub, name=payload.name
    )
    return await _issue_tokens(db, user.id, user.email, user.is_email_verified)


@router.post("/refresh", response_model=RefreshResponse)
async def refresh(payload: RefreshRequest) -> RefreshResponse:
    try:
        claims = decode_jwt(payload.refresh_token, expected_type="refresh")
    except jwt.InvalidTokenError as exc:
        raise UnauthenticatedError("Invalid or expired refresh token.") from exc

    return RefreshResponse(access_token=issue_access_token(claims["sub"]))
