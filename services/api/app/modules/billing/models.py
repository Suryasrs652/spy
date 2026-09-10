"""§79 subscriptions, §80 plans, §81 purchases, §82/§13 webhook_events."""
from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPKMixin, utcnow


class BillingInterval(StrEnum):
    MONTHLY = "MONTHLY"
    ONE_TIME = "ONE_TIME"


class Plan(UUIDPKMixin, Base):
    """§80 — pricing lives in DB, never hard-coded in frontend or backend."""

    __tablename__ = "plans"

    code: Mapped[str] = mapped_column(String(30), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)

    price_minor: Mapped[int] = mapped_column(BigInteger, nullable=False)  # paise
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="INR")

    billing_interval: Mapped[str] = mapped_column(String(20), nullable=False)

    audit_limit: Mapped[int | None] = mapped_column(Integer)
    crawl_url_limit: Mapped[int] = mapped_column(Integer, nullable=False, default=500)
    project_limit: Mapped[int | None] = mapped_column(Integer)
    member_limit: Mapped[int | None] = mapped_column(Integer)

    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class SubscriptionStatus(StrEnum):
    ACTIVE = "ACTIVE"
    PAUSED = "PAUSED"
    CANCELLED = "CANCELLED"
    PAST_DUE = "PAST_DUE"
    COMPLETED = "COMPLETED"


class Subscription(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "subscriptions"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )

    provider: Mapped[str] = mapped_column(String(30), nullable=False, default="razorpay")
    provider_subscription_id: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)

    plan_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("plans.id"), nullable=False)

    status: Mapped[str] = mapped_column(String(20), nullable=False, default=SubscriptionStatus.ACTIVE.value)

    current_period_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    current_period_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    cancel_at_period_end: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class PurchaseStatus(StrEnum):
    PENDING = "PENDING"
    PAID = "PAID"
    FAILED = "FAILED"


class Purchase(UUIDPKMixin, Base):
    __tablename__ = "purchases"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )

    provider: Mapped[str] = mapped_column(String(30), nullable=False, default="razorpay")
    provider_order_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    provider_payment_id: Mapped[str | None] = mapped_column(String(100))

    product_type: Mapped[str] = mapped_column(String(30), nullable=False, default="SINGLE_AUDIT")

    amount_minor: Mapped[int] = mapped_column(BigInteger, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="INR")

    status: Mapped[str] = mapped_column(String(20), nullable=False, default=PurchaseStatus.PENDING.value)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class WebhookStatus(StrEnum):
    RECEIVED = "RECEIVED"
    PROCESSED = "PROCESSED"
    IGNORED = "IGNORED"
    ERROR = "ERROR"


class WebhookEvent(UUIDPKMixin, Base):
    """§13/§82/§121 — provider_event_id UNIQUE is the idempotency anchor.

    A duplicate delivery hits the unique constraint on insert; the handler
    catches that specific IntegrityError, returns HTTP 200, and does nothing
    else. This is what makes it structurally impossible to grant a credit
    twice for one Razorpay event, independent of any application-level
    "already processed?" check that could itself race.
    """

    __tablename__ = "webhook_events"

    provider: Mapped[str] = mapped_column(String(30), nullable=False)
    provider_event_id: Mapped[str] = mapped_column(String(150), unique=True, nullable=False)
    event_type: Mapped[str] = mapped_column(String(50), nullable=False)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)

    status: Mapped[str] = mapped_column(String(20), nullable=False, default=WebhookStatus.RECEIVED.value)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error: Mapped[str | None] = mapped_column(Text)
