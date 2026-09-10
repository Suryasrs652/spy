"""§84 recommendations, §51 priority score."""
from __future__ import annotations

import uuid
from enum import StrEnum

from sqlalchemy import ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPKMixin


class RecommendationStatus(StrEnum):
    OPEN = "OPEN"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    DISMISSED = "DISMISSED"


class RecommendationGroup(StrEnum):
    DO_NOW = "DO_NOW"
    THIS_WEEK = "THIS_WEEK"
    THIS_MONTH = "THIS_MONTH"
    MONITOR = "MONITOR"


class Recommendation(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "recommendations"

    audit_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("audits.id", ondelete="CASCADE"), nullable=False, index=True
    )

    category: Mapped[str] = mapped_column(String(50), nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)

    impact: Mapped[int] = mapped_column(Integer, nullable=False)
    confidence: Mapped[int] = mapped_column(Integer, nullable=False)
    effort: Mapped[int] = mapped_column(Integer, nullable=False)
    priority_score: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False)

    status: Mapped[str] = mapped_column(String(20), nullable=False, default=RecommendationStatus.OPEN.value)
    # §52 Action Center bucket (Do Now / This Week / This Month / Monitor),
    # computed once at creation from priority_score+severity and stored so
    # re-tuning the thresholds later doesn't reshuffle an already-viewed list.
    group: Mapped[str] = mapped_column(String(20), nullable=False, default=RecommendationGroup.MONITOR.value)

    evidence: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
