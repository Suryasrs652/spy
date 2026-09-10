"""Auth + tenant-isolation dependencies.

§86: tenant isolation is a dependency, not a convention. `require_org`
resolves (user, organization, role) from the bearer access token plus the
X-Organization-Id header, checking real membership in `organization_members`
on every request. Every module's service functions additionally take
`organization_id` as a required first argument and filter every query by it
so a mismatched or spoofed id can never surface another tenant's row — a
cross-tenant lookup returns 404, never a 403 that would confirm existence
(§122).
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass

import jwt
from fastapi import Depends, Header
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ForbiddenError, NotFoundError, UnauthenticatedError
from app.core.security import decode_jwt
from app.db.session import get_db
from app.modules.auth.models import User, UserStatus
from app.modules.organizations.models import OrganizationMember, OrgRole


@dataclass(frozen=True)
class AuthContext:
    user_id: uuid.UUID
    organization_id: uuid.UUID
    role: OrgRole


def _extract_bearer(authorization: str | None) -> str:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise UnauthenticatedError("Missing or malformed Authorization header.")
    return authorization.split(" ", 1)[1].strip()


async def get_current_user(
    authorization: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db),
) -> User:
    token = _extract_bearer(authorization)
    try:
        payload = decode_jwt(token, expected_type="access")
    except jwt.InvalidTokenError as exc:
        raise UnauthenticatedError("Invalid or expired session.") from exc

    user_id = uuid.UUID(payload["sub"])
    user = (await db.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
    if user is None or user.status != UserStatus.ACTIVE.value:
        raise UnauthenticatedError("Account is not active.")
    return user


async def get_auth_context(
    x_organization_id: str = Header(..., alias="X-Organization-Id"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> AuthContext:
    try:
        org_id = uuid.UUID(x_organization_id)
    except ValueError as exc:
        raise NotFoundError("Organization not found.") from exc

    membership = (
        await db.execute(
            select(OrganizationMember).where(
                OrganizationMember.organization_id == org_id,
                OrganizationMember.user_id == user.id,
            )
        )
    ).scalar_one_or_none()

    if membership is None:
        # Do not distinguish "org doesn't exist" from "you're not a member" —
        # both must look identical to the caller (§122).
        raise NotFoundError("Organization not found.")

    return AuthContext(user_id=user.id, organization_id=org_id, role=OrgRole(membership.role))


def require_role(*allowed: OrgRole):
    async def _dep(ctx: AuthContext = Depends(get_auth_context)) -> AuthContext:
        if ctx.role not in allowed:
            raise ForbiddenError("You do not have permission to perform this action.")
        return ctx

    return _dep
