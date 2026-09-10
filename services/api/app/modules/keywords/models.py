"""§144/M5 — rank tracking, built entirely on Search Console data Spy has
already synced (app/modules/gsc/sync_service.py) rather than a live SERP
checker: scraping Google's result pages would violate its Terms of Service
and there is no free, legitimate API for arbitrary keyword rank checks.
GSC's own `position` field is Google-reported and real, just narrower in
scope than a general rank tracker (it only has data for queries the site
actually received impressions for, and only after a sync has run) —
real evidence, not manufactured (§3), with an honestly narrower coverage
than "check any keyword's rank on demand."
"""
from __future__ import annotations

import uuid

from sqlalchemy import ForeignKey, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPKMixin


class TrackedKeyword(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "tracked_keywords"
    __table_args__ = (UniqueConstraint("project_id", "keyword", name="uq_tracked_keyword_project"),)

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    keyword: Mapped[str] = mapped_column(Text, nullable=False)
    added_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
