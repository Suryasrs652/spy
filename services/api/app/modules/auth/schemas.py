from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class SignupRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    name: str | None = None


class SignupResponse(BaseModel):
    user_id: uuid.UUID
    organization_id: uuid.UUID
    email: EmailStr


class VerifyEmailRequest(BaseModel):
    token: str


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str = Field(min_length=8, max_length=128)


class MeResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    email_verified: bool
    created_at: datetime


# ── internal (service-to-service, Next.js Auth.js -> FastAPI) ──────────
class VerifyCredentialsRequest(BaseModel):
    email: EmailStr
    password: str


class OAuthUpsertRequest(BaseModel):
    email: EmailStr
    google_sub: str
    name: str | None = None


class InternalUserOut(BaseModel):
    user_id: uuid.UUID
    email: EmailStr
    email_verified: bool
    default_organization_id: uuid.UUID
    access_token: str
    refresh_token: str


class RefreshRequest(BaseModel):
    refresh_token: str


class RefreshResponse(BaseModel):
    access_token: str
