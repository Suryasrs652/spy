"""§88 public auth endpoints."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user
from app.core.ratelimit import rate_limit_dependency
from app.db.session import get_db
from app.modules.auth import service
from app.modules.auth.models import User
from app.modules.auth.schemas import (
    ForgotPasswordRequest,
    MeResponse,
    ResetPasswordRequest,
    SignupRequest,
    SignupResponse,
    VerifyEmailRequest,
)

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post(
    "/signup",
    response_model=SignupResponse,
    status_code=201,
    dependencies=[Depends(rate_limit_dependency("signup", limit=5, window_seconds=60))],
)
async def signup(payload: SignupRequest, db: AsyncSession = Depends(get_db)) -> SignupResponse:
    user, org_id = await service.signup(
        db, email=payload.email, password=payload.password, name=payload.name
    )
    return SignupResponse(user_id=user.id, organization_id=org_id, email=user.email)


@router.post("/verify-email", status_code=200)
async def verify_email(payload: VerifyEmailRequest, db: AsyncSession = Depends(get_db)) -> dict:
    await service.verify_email(db, token=payload.token)
    return {"verified": True}


@router.post(
    "/forgot-password",
    status_code=202,
    dependencies=[Depends(rate_limit_dependency("forgot_password", limit=5, window_seconds=60))],
)
async def forgot_password(payload: ForgotPasswordRequest, db: AsyncSession = Depends(get_db)) -> dict:
    await service.request_password_reset(db, email=payload.email)
    return {"message": "If an account exists for that email, a reset link has been sent."}


@router.post("/reset-password", status_code=200)
async def reset_password(payload: ResetPasswordRequest, db: AsyncSession = Depends(get_db)) -> dict:
    await service.reset_password(db, token=payload.token, new_password=payload.new_password)
    return {"reset": True}


@router.get("/me", response_model=MeResponse)
async def me(user: User = Depends(get_current_user)) -> MeResponse:
    return MeResponse(
        id=user.id,
        email=user.email,
        email_verified=user.is_email_verified,
        created_at=user.created_at,
    )
