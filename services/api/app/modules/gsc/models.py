"""§71-§73 GSC connection/property/metrics tables.

Tables and OAuth connect flow ship in M1; the daily sync job (§33) and
opportunity engine (§34) are M2. GSC_ENABLED feature flag gates the UI.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime
from enum import StrEnum

from sqlalchemy import ARRAY, BigInteger, Boolean, Date, DateTime, ForeignKey, Numeric, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, UUIDPKMixin, utcnow


class GscConnectionStatus(StrEnum):
    ACTIVE = "ACTIVE"
    REVOKED = "REVOKED"
    ERROR = "ERROR"


class GscConnection(UUIDPKMixin, Base):
    __tablename__ = "gsc_connections"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)

    google_account_id: Mapped[str] = mapped_column(String(100), nullable=False)

    # §106: encrypted at rest with app.core.security.encrypt_secret (Fernet),
    # never stored or logged in plaintext.
    encrypted_refresh_token: Mapped[str] = mapped_column(Text, nullable=False)
    scopes: Mapped[list[str]] = mapped_column(ARRAY(String), nullable=False, default=list)

    status: Mapped[str] = mapped_column(String(20), nullable=False, default=GscConnectionStatus.ACTIVE.value)

    connected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    last_sync_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class GscProperty(UUIDPKMixin, Base):
    __tablename__ = "gsc_properties"

    connection_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("gsc_connections.id", ondelete="CASCADE"), nullable=False, index=True
    )
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="SET NULL"), nullable=True
    )

    site_url: Mapped[str] = mapped_column(Text, nullable=False)
    permission_level: Mapped[str] = mapped_column(String(30), nullable=False)
    selected: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class GscDailyMetric(Base):
    """§73 — bigserial PK; partition by date once volume warrants it (§73)."""

    __tablename__ = "gsc_daily_metrics"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)

    property_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("gsc_properties.id", ondelete="CASCADE"), nullable=False, index=True
    )

    date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    query: Mapped[str | None] = mapped_column(Text)
    page: Mapped[str | None] = mapped_column(Text)
    country: Mapped[str | None] = mapped_column(String(10))
    device: Mapped[str | None] = mapped_column(String(20))
    search_type: Mapped[str] = mapped_column(String(20), nullable=False, default="web")

    clicks: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    impressions: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    ctr: Mapped[float] = mapped_column(Numeric(6, 4), nullable=False, default=0)
    position: Mapped[float] = mapped_column(Numeric(6, 2), nullable=False, default=0)
