"""§69 audit_issues, §70 audit_issue_pages, §24 severity."""
from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, UUIDPKMixin, utcnow


class Severity(StrEnum):
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    INFO = "INFO"


SEVERITY_ORDER = {s: i for i, s in enumerate(
    [Severity.CRITICAL, Severity.HIGH, Severity.MEDIUM, Severity.LOW, Severity.INFO]
)}


class AuditIssue(UUIDPKMixin, Base):
    __tablename__ = "audit_issues"

    audit_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("audits.id", ondelete="CASCADE"), nullable=False, index=True
    )

    rule_id: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    category: Mapped[str] = mapped_column(String(50), nullable=False)
    severity: Mapped[str] = mapped_column(String(20), nullable=False)

    title: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    recommendation: Mapped[str] = mapped_column(Text, nullable=False)

    affected_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    score_impact: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False, default=0)

    # 0-1: how much of this finding is observation rather than inference.
    # Declared per rule (app/modules/seo/rules/base.py) and carried through to
    # the priority formula, so "possible keyword stuffing" cannot outrank a
    # missing title on affected-page count alone.
    confidence: Mapped[float] = mapped_column(Numeric(3, 2), nullable=False, default=1.0)

    # Whether a human or the evidence-validator agent has since checked this
    # finding against the live site. NULL is the honest default and means
    # *unchecked* — deliberately distinct from False, which is a recorded
    # verdict that the finding did not hold up.
    validated: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    validated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Why the verdict went the way it did — the part a reader actually needs
    # when a finding is marked false ("canonical is there, injected by JS").
    validation_note: Mapped[str | None] = mapped_column(Text)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class AuditIssuePage(Base):
    __tablename__ = "audit_issue_pages"

    issue_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("audit_issues.id", ondelete="CASCADE"), primary_key=True
    )
    page_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("crawl_pages.id", ondelete="CASCADE"), primary_key=True
    )
    evidence: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
