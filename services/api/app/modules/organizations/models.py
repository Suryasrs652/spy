"""§61-§62 organizations + membership. §14 role model."""
from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPKMixin, utcnow


class OrgRole(StrEnum):
    OWNER = "OWNER"
    ADMIN = "ADMIN"
    ANALYST = "ANALYST"
    VIEWER = "VIEWER"


# Permission matrix consumed by app.core.deps.require_org. Keep centralized
# so role capability changes are one-line edits, not scattered conditionals.
ROLE_CAN_MANAGE_BILLING = {OrgRole.OWNER}
ROLE_CAN_MANAGE_MEMBERS = {OrgRole.OWNER, OrgRole.ADMIN}
ROLE_CAN_DELETE_ORG = {OrgRole.OWNER}
ROLE_CAN_MANAGE_PROJECTS = {OrgRole.OWNER, OrgRole.ADMIN}
ROLE_CAN_RUN_AUDITS = {OrgRole.OWNER, OrgRole.ADMIN, OrgRole.ANALYST}
ROLE_CAN_VIEW = {OrgRole.OWNER, OrgRole.ADMIN, OrgRole.ANALYST, OrgRole.VIEWER}


class Organization(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "organizations"

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    slug: Mapped[str] = mapped_column(String(220), unique=True, nullable=False, index=True)
    owner_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )


class OrganizationMember(Base):
    __tablename__ = "organization_members"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), primary_key=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    role: Mapped[str] = mapped_column(String(20), nullable=False, default=OrgRole.OWNER.value)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
