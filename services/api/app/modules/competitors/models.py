"""§144/M5 — competitor benchmarking.

Deliberately outside the paid-entitlement audit system (app/modules/
entitlements): a competitor site isn't the user's own property, so "spend
your free/purchased audit credit crawling someone else's site" would be a
confusing, possibly resented default with no clear right answer — and this
isn't a policy this repo is positioned to decide unilaterally. Instead this
runs a smaller, uncounted benchmark crawl (see MAX_COMPETITOR_URLS in
service.py) reusing the same real rule engine and scoring pipeline
(app/modules/seo/rules, app/modules/scoring) — real evidence, just a
shallower crawl than a full paid audit, and no entitlement consumed.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import DateTime, ForeignKey, Numeric, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPKMixin


class CompetitorStatus(StrEnum):
    PENDING = "PENDING"
    CRAWLING = "CRAWLING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class Competitor(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "competitors"
    __table_args__ = (UniqueConstraint("project_id", "canonical_origin", name="uq_competitor_project_origin"),)

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    added_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    domain: Mapped[str] = mapped_column(String(255), nullable=False)
    canonical_origin: Mapped[str] = mapped_column(Text, nullable=False)

    status: Mapped[str] = mapped_column(String(20), nullable=False, default=CompetitorStatus.PENDING.value)
    last_crawled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    failure_message: Mapped[str | None] = mapped_column(Text)

    spy_score: Mapped[float | None] = mapped_column(Numeric(5, 2))
    technical_score: Mapped[float | None] = mapped_column(Numeric(5, 2))
    seo_score: Mapped[float | None] = mapped_column(Numeric(5, 2))
    content_score: Mapped[float | None] = mapped_column(Numeric(5, 2))
    performance_score: Mapped[float | None] = mapped_column(Numeric(5, 2))
    aeo_score: Mapped[float | None] = mapped_column(Numeric(5, 2))
    geo_score: Mapped[float | None] = mapped_column(Numeric(5, 2))

    evidence: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
