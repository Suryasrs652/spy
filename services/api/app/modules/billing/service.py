"""§12-§13, §80-§82, §95, §120-§121 — Razorpay checkout + webhook handling.

The browser never grants itself anything: `create_order` only creates a
PENDING `Purchase` row and a Razorpay order id for Checkout to use.
Payment is only ever recognized through `handle_webhook_event`, which is
called solely from the signature-verified webhook route.
"""
from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.errors import NotFoundError, ValidationAppError
from app.db.base import utcnow
from app.modules.billing.models import (
    Plan,
    Purchase,
    PurchaseStatus,
    WebhookEvent,
    WebhookStatus,
)
from app.modules.billing.razorpay_client import create_order as razorpay_create_order
from app.modules.entitlements.models import AuditEntitlement, EntitlementStatus, EntitlementType
from app.modules.notifications.service import notify_purchase_failed, notify_purchase_succeeded
from app.modules.organizations.models import Organization


async def get_plans(db: AsyncSession) -> list[Plan]:
    result = await db.execute(select(Plan).where(Plan.active.is_(True)))
    return list(result.scalars().all())


async def create_order(db: AsyncSession, *, organization_id: uuid.UUID, plan_code: str) -> tuple[Purchase, str]:
    plan = (await db.execute(select(Plan).where(Plan.code == plan_code, Plan.active.is_(True)))).scalar_one_or_none()
    if plan is None:
        raise ValidationAppError(f"Unknown plan code {plan_code!r}.")

    purchase = Purchase(
        organization_id=organization_id,
        provider="razorpay",
        provider_order_id="",  # filled in below once Razorpay responds
        product_type=plan.code,
        amount_minor=plan.price_minor,
        currency=plan.currency,
        status=PurchaseStatus.PENDING.value,
    )
    db.add(purchase)
    await db.flush()

    order = razorpay_create_order(
        amount_minor=plan.price_minor,
        currency=plan.currency,
        receipt=str(purchase.id),
        notes={"organization_id": str(organization_id), "plan_code": plan.code, "purchase_id": str(purchase.id)},
    )
    purchase.provider_order_id = order["id"]
    await db.commit()
    await db.refresh(purchase)

    return purchase, get_settings().razorpay_key_id


async def record_webhook_event(
    db: AsyncSession, *, provider_event_id: str, event_type: str, payload: dict
) -> bool:
    """Returns True if this is a new event that should be processed, False
    if it's a duplicate delivery (§13/§121) — the caller returns HTTP 200
    either way, but only processes side effects on True.
    """
    event = WebhookEvent(
        provider="razorpay", provider_event_id=provider_event_id, event_type=event_type, payload=payload,
    )
    db.add(event)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        return False
    return True


async def _org_owner(db: AsyncSession, organization_id: uuid.UUID):
    from app.modules.auth.models import User

    org = (await db.execute(select(Organization).where(Organization.id == organization_id))).scalar_one_or_none()
    if org is None:
        return None
    return (await db.execute(select(User).where(User.id == org.owner_user_id))).scalar_one_or_none()


async def process_payment_captured(db: AsyncSession, *, order_id: str, payment_id: str) -> None:
    purchase = (
        await db.execute(select(Purchase).where(Purchase.provider_order_id == order_id))
    ).scalar_one_or_none()
    if purchase is None:
        return  # unknown order — nothing to grant; logged by the caller

    if purchase.status == PurchaseStatus.PAID.value:
        return  # already processed (defensive; webhook_events uniqueness is the primary guard)

    purchase.status = PurchaseStatus.PAID.value
    purchase.provider_payment_id = payment_id
    purchase.paid_at = utcnow()

    db.add(
        AuditEntitlement(
            organization_id=purchase.organization_id,
            type=EntitlementType.PURCHASED.value,
            status=EntitlementStatus.AVAILABLE.value,
            quantity=1,
            remaining=1,
            source=f"RAZORPAY_PURCHASE:{purchase.id}",
        )
    )
    await db.commit()

    owner = await _org_owner(db, purchase.organization_id)
    if owner is not None:
        await notify_purchase_succeeded(db, purchase=purchase, owner_user_id=owner.id, owner_email=owner.email)


async def process_payment_failed(db: AsyncSession, *, order_id: str) -> None:
    purchase = (
        await db.execute(select(Purchase).where(Purchase.provider_order_id == order_id))
    ).scalar_one_or_none()
    if purchase is None:
        return
    if purchase.status == PurchaseStatus.PENDING.value:
        purchase.status = PurchaseStatus.FAILED.value
        await db.commit()

        owner = await _org_owner(db, purchase.organization_id)
        if owner is not None:
            await notify_purchase_failed(db, purchase=purchase, owner_user_id=owner.id, owner_email=owner.email)
