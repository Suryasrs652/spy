"""§65, §8-§9 audit entitlements — the commercial core.

The partial unique index below is what makes the free-audit race (§8)
impossible at the database level: at most one "live" FREE_LIFETIME row can
ever exist per user, regardless of how many concurrent requests race to
create one. See alembic/versions for the migration that creates it.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPKMixin


class EntitlementType(StrEnum):
    FREE_LIFETIME = "FREE_LIFETIME"
    PURCHASED = "PURCHASED"
    SUBSCRIPTION = "SUBSCRIPTION"
    ADMIN_GRANT = "ADMIN_GRANT"


class EntitlementStatus(StrEnum):
    AVAILABLE = "AVAILABLE"
    RESERVED = "RESERVED"
    CONSUMED = "CONSUMED"
    RELEASED = "RELEASED"
    EXPIRED = "EXPIRED"


# Statuses that count as "this entitlement is live" for uniqueness purposes.
LIVE_ENTITLEMENT_STATUSES = (
    EntitlementStatus.AVAILABLE,
    EntitlementStatus.RESERVED,
    EntitlementStatus.CONSUMED,
)


class AuditEntitlement(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "audit_entitlements"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )

    type: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=EntitlementStatus.AVAILABLE.value
    )

    audit_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("audits.id", ondelete="SET NULL"), nullable=True
    )

    quantity: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    remaining: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    source: Mapped[str] = mapped_column(String(100), nullable=False, default="SYSTEM")

    reserved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
