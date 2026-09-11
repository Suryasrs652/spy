"""Request context dependencies.

Spy is self-hosted and single-user (see `app.core.local_workspace`), so
there is nothing to authenticate: every request resolves to the same
local user and organization, with the highest role.

These dependencies keep the exact shapes they had when this was a
multi-tenant SaaS — `AuthContext(user_id, organization_id, role)`,
`require_role(...)`, `require_super_admin` — because every router and
service downstream is written against them and still filters every query
by `organization_id`. Putting real auth back means changing this file
(and `local_workspace`), not the ~15 modules that depend on it.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.local_workspace import LOCAL_ORG_ID, get_local_user
from app.db.session import get_db
from app.modules.auth.models import User
from app.modules.organizations.models import OrgRole


@dataclass(frozen=True)
class AuthContext:
    user_id: uuid.UUID
    organization_id: uuid.UUID
    role: OrgRole


async def get_current_user(db: AsyncSession = Depends(get_db)) -> User:
    return await get_local_user(db)


async def get_auth_context(user: User = Depends(get_current_user)) -> AuthContext:
    return AuthContext(user_id=user.id, organization_id=LOCAL_ORG_ID, role=OrgRole.OWNER)


def require_role(*allowed: OrgRole):
    """Kept as a decorator-shaped dependency so call sites are unchanged.

    The local operator is always OWNER, which every ROLE_CAN_* set in
    `app.modules.organizations.models` includes, so this never rejects —
    but the permission matrix stays wired up and meaningful for the day
    multi-user comes back.
    """

    async def _dep(ctx: AuthContext = Depends(get_auth_context)) -> AuthContext:
        return ctx

    return _dep


async def require_super_admin(user: User = Depends(get_current_user)) -> User:
    """Self-hosted: whoever is running the instance owns it, so the admin
    surface is simply open rather than gated on a flag nobody else could
    have set."""
    return user
