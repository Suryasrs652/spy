"""The single workspace this self-hosted instance runs as.

Spy is a self-hosted, single-user tool: you clone the repo and run it on
your own machine, so there is no sign-up, no login, and no tenancy to
enforce between people. What there *is* — still — is an
`organization_id` on every table and a `require_org`-shaped dependency in
front of every endpoint. That's deliberate: keeping the column and the
dependency means every module's queries, services and tests stay exactly
as they were, and re-introducing real multi-user auth later is a change
to this one file rather than to every query in the codebase.

So instead of resolving a tenant from a token, we resolve to one fixed,
auto-provisioned local user + organization. The ids are constants rather
than generated so a restart, a fresh volume, or a second worker process
all converge on the same rows.
"""
from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import utcnow
from app.modules.auth.models import User
from app.modules.organizations.models import Organization, OrganizationMember, OrgRole

LOCAL_USER_ID = uuid.UUID("00000000-0000-0000-0000-00000000513f")
LOCAL_ORG_ID = uuid.UUID("00000000-0000-0000-0000-0000000005e0")
LOCAL_USER_EMAIL = "local@spy.local"
LOCAL_ORG_NAME = "My Workspace"
LOCAL_ORG_SLUG = "local"

# Set once the rows are known to exist so the common path is a no-op
# rather than a SELECT on every single request.
_provisioned = False


async def ensure_local_workspace(db: AsyncSession) -> None:
    """Create the local user + organization if they aren't there yet.

    Idempotent and safe to call concurrently: the ids are fixed, so a race
    loses on the primary key and simply re-reads the winner's rows.
    """
    global _provisioned
    if _provisioned:
        return

    existing = await db.get(Organization, LOCAL_ORG_ID)
    if existing is not None:
        _provisioned = True
        return

    db.add(
        User(
            id=LOCAL_USER_ID,
            email=LOCAL_USER_EMAIL,
            # No email round-trip exists to verify through, and several
            # flows still read this; treat the local operator as verified.
            email_verified_at=utcnow(),
        )
    )
    await db.flush()
    db.add(
        Organization(
            id=LOCAL_ORG_ID, name=LOCAL_ORG_NAME, slug=LOCAL_ORG_SLUG, owner_user_id=LOCAL_USER_ID
        )
    )
    await db.flush()
    db.add(
        OrganizationMember(
            organization_id=LOCAL_ORG_ID, user_id=LOCAL_USER_ID, role=OrgRole.OWNER.value
        )
    )

    try:
        await db.commit()
    except IntegrityError:
        # Another request/worker provisioned it first — its rows are
        # identical, so just adopt them.
        await db.rollback()

    _provisioned = True


async def get_local_user(db: AsyncSession) -> User:
    await ensure_local_workspace(db)
    user = (await db.execute(select(User).where(User.id == LOCAL_USER_ID))).scalar_one()
    return user
