"""Organization creation and membership helpers."""
from __future__ import annotations

import uuid

from slugify import slugify
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.organizations.models import Organization, OrganizationMember, OrgRole


async def _unique_slug(db: AsyncSession, base: str) -> str:
    base_slug = slugify(base) or "workspace"
    slug = base_slug
    suffix = 0
    while True:
        existing = (
            await db.execute(select(Organization).where(Organization.slug == slug))
        ).scalar_one_or_none()
        if existing is None:
            return slug
        suffix += 1
        slug = f"{base_slug}-{suffix}"


async def create_organization_with_owner(
    db: AsyncSession, *, name: str, owner_user_id: uuid.UUID
) -> Organization:
    """§18 — a workspace is created alongside signup so every audit-related
    row (projects, entitlements, audits) always has an organization_id from
    the start. The user can rename it later ("Create Workspace" screen).
    """
    slug = await _unique_slug(db, name)
    org = Organization(name=name, slug=slug, owner_user_id=owner_user_id)
    db.add(org)
    await db.flush()

    db.add(OrganizationMember(organization_id=org.id, user_id=owner_user_id, role=OrgRole.OWNER.value))
    return org


async def list_user_organizations(db: AsyncSession, user_id: uuid.UUID) -> list[Organization]:
    result = await db.execute(
        select(Organization)
        .join(OrganizationMember, OrganizationMember.organization_id == Organization.id)
        .where(OrganizationMember.user_id == user_id)
        .order_by(Organization.created_at)
    )
    return list(result.scalars().all())
