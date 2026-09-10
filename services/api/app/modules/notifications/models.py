"""§134 in-app + email notifications.

Always addressed to one user (never "all org members" fan-out) — the
service functions below decide who that is per event type (the audit
requester for audit lifecycle events, the org owner for billing events).
Kept deliberately simple: no per-user notification preferences yet, no
push/SMS channel — just in-app list + a best-effort transactional email via
the same MailHog-backed sender used for verification/reset emails.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, UUIDPKMixin, utcnow


class NotificationType(StrEnum):
    AUDIT_COMPLETED = "AUDIT_COMPLETED"
    AUDIT_FAILED = "AUDIT_FAILED"
    PURCHASE_SUCCEEDED = "PURCHASE_SUCCEEDED"
    PURCHASE_FAILED = "PURCHASE_FAILED"


class Notification(UUIDPKMixin, Base):
    __tablename__ = "notifications"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )

    type: Mapped[str] = mapped_column(String(50), nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    # Frontend-relative link the notification should navigate to when
    # clicked, e.g. "/audits/{id}" — never a full URL (avoids ever storing
    # an environment-specific host in a row that might outlive one).
    link_path: Mapped[str | None] = mapped_column(String(500))

    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
