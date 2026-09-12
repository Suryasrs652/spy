"""§64 audits, §66 audit_jobs, §29 job states, §30 failure taxonomy."""
from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import DateTime, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPKMixin

CURRENT_SCORE_VERSION = "spy-score-v1.0"


class AuditStatus(StrEnum):
    QUEUED = "QUEUED"
    PREPARING = "PREPARING"
    CRAWLING = "CRAWLING"
    ANALYZING = "ANALYZING"
    SCORING = "SCORING"
    GENERATING_REPORT = "GENERATING_REPORT"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


TERMINAL_STATUSES = (AuditStatus.COMPLETED, AuditStatus.FAILED, AuditStatus.CANCELLED)


class FailureCategory(StrEnum):
    USER_ERROR = "USER_ERROR"
    TARGET_ERROR = "TARGET_ERROR"
    SYSTEM_ERROR = "SYSTEM_ERROR"
    THIRD_PARTY_ERROR = "THIRD_PARTY_ERROR"


class FailureCode(StrEnum):
    DNS_FAILURE = "DNS_FAILURE"
    TIMEOUT = "TIMEOUT"
    ROBOTS_BLOCKED = "ROBOTS_BLOCKED"
    RATE_LIMITED = "RATE_LIMITED"
    SSL_ERROR = "SSL_ERROR"
    DATABASE_ERROR = "DATABASE_ERROR"
    WORKER_ERROR = "WORKER_ERROR"
    BLOCKED_TARGET = "BLOCKED_TARGET"
    NO_CRAWLABLE_HTML = "NO_CRAWLABLE_HTML"
    UNREACHABLE = "UNREACHABLE"
    CANCELLED_BY_USER = "CANCELLED_BY_USER"


# §4/§30/§119: failure codes that RELEASE the reserved entitlement rather
# than consuming it. Everything else in FailureCode also releases — there is
# currently no failure code that both fails the audit and keeps the credit
# spent — but this explicit allowlist is what the entitlement service reads,
# so adding a "the user's fault, spend it anyway" code later is a one-line,
# reviewable change here rather than an implicit default.
RELEASE_ON_FAILURE = frozenset(FailureCode)


class Audit(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "audits"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    requested_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )

    audit_type: Mapped[str] = mapped_column(String(30), nullable=False, default="FULL")
    status: Mapped[str] = mapped_column(String(30), nullable=False, default=AuditStatus.QUEUED.value)

    max_urls: Mapped[int] = mapped_column(Integer, nullable=False, default=500)

    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    spy_score: Mapped[float | None] = mapped_column(Numeric(5, 2))
    technical_score: Mapped[float | None] = mapped_column(Numeric(5, 2))
    seo_score: Mapped[float | None] = mapped_column(Numeric(5, 2))  # §20 "SEO Score" card (on-page + images + schema)
    content_score: Mapped[float | None] = mapped_column(Numeric(5, 2))
    performance_score: Mapped[float | None] = mapped_column(Numeric(5, 2))
    authority_score: Mapped[float | None] = mapped_column(Numeric(5, 2))
    aeo_score: Mapped[float | None] = mapped_column(Numeric(5, 2))
    geo_score: Mapped[float | None] = mapped_column(Numeric(5, 2))
    acrs_score: Mapped[float | None] = mapped_column(Numeric(5, 2))
    confidence: Mapped[float | None] = mapped_column(Numeric(5, 2))

    # §21: "Scores must include: score, confidence, evidence, affected_pages,
    # calculation_version" — this JSONB blob is that evidence (per-component
    # weights actually used, AEO/GEO signal breakdown, internal-architecture
    # sub-score, page-count basis for confidence). Immutable once the audit
    # is COMPLETED, same as score_version (§132).
    evidence: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    score_version: Mapped[str] = mapped_column(String(30), nullable=False, default=CURRENT_SCORE_VERSION)

    failure_category: Mapped[str | None] = mapped_column(String(30))
    failure_code: Mapped[str | None] = mapped_column(String(50))
    failure_message: Mapped[str | None] = mapped_column(Text)


class AuditJob(UUIDPKMixin, Base):
    __tablename__ = "audit_jobs"

    audit_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("audits.id", ondelete="CASCADE"), unique=True, nullable=False
    )

    status: Mapped[str] = mapped_column(String(30), nullable=False, default=AuditStatus.QUEUED.value)
    progress: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    urls_discovered: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    urls_processed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    queue_job_id: Mapped[str | None] = mapped_column(String(100))
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    error_code: Mapped[str | None] = mapped_column(String(50))
    error_detail: Mapped[str | None] = mapped_column(Text)
