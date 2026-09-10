"""§83 reports."""
from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, UUIDPKMixin, utcnow


class ReportFormat(StrEnum):
    PDF = "PDF"
    CSV = "CSV"
    WEB = "WEB"


class ReportStatus(StrEnum):
    PENDING = "PENDING"
    GENERATING = "GENERATING"
    READY = "READY"
    FAILED = "FAILED"


class Report(UUIDPKMixin, Base):
    __tablename__ = "reports"

    audit_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("audits.id", ondelete="CASCADE"), nullable=False, index=True
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )

    format: Mapped[str] = mapped_column(String(10), nullable=False, default=ReportFormat.PDF.value)
    storage_key: Mapped[str | None] = mapped_column(Text)

    status: Mapped[str] = mapped_column(String(20), nullable=False, default=ReportStatus.PENDING.value)

    generated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
