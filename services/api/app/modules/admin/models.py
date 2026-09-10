"""§130 feature_flags, §131 rule_config, §85 audit_logs, §99 idempotency_keys."""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, utcnow


class FeatureFlag(Base):
    __tablename__ = "feature_flags"

    key: Mapped[str] = mapped_column(String(50), primary_key=True)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    config: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)


class RuleConfig(TimestampMixin, Base):
    """§131 — versioned, configurable audit-rule thresholds.

    A completed audit stores the rule_config version it used (implicitly via
    the audit's score_version); changing a threshold here only affects
    audits run after the change, never recomputes history (§132).
    """

    __tablename__ = "rule_config"

    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    version: Mapped[str] = mapped_column(String(30), primary_key=True)
    value: Mapped[dict] = mapped_column(JSONB, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)

    organization_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True, index=True)
    user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True, index=True)

    action: Mapped[str] = mapped_column(String(100), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(50), nullable=False)
    entity_id: Mapped[str] = mapped_column(String(100), nullable=False)

    ip_hash: Mapped[str | None] = mapped_column(String(64))
    metadata_json: Mapped[dict] = mapped_column("metadata", JSONB, nullable=False, default=dict)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class IdempotencyKey(Base):
    """§99 — backs the Idempotency-Key header on audit/purchase/report creation."""

    __tablename__ = "idempotency_keys"

    key: Mapped[str] = mapped_column(String(200), primary_key=True)
    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    endpoint: Mapped[str] = mapped_column(String(200), nullable=False)
    response_status: Mapped[int] = mapped_column(nullable=False)
    response_body: Mapped[dict] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
