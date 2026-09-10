from __future__ import annotations

import structlog
from fastapi import APIRouter, Depends, Header, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.deps import AuthContext, require_role
from app.core.errors import UnauthenticatedError
from app.db.session import get_db
from app.modules.billing import service
from app.modules.billing.schemas import (
    BillingStatusOut,
    CreateOrderRequest,
    CreateOrderResponse,
    PlanOut,
)
from app.modules.billing.razorpay_client import verify_webhook_signature
from app.modules.organizations.models import ROLE_CAN_MANAGE_BILLING

logger = structlog.get_logger(__name__)

router = APIRouter(tags=["billing"])


@router.get("/billing/plans", response_model=list[PlanOut])
async def list_plans(db: AsyncSession = Depends(get_db)) -> list[PlanOut]:
    plans = await service.get_plans(db)
    return [PlanOut.model_validate(p) for p in plans]


@router.post("/billing/order", response_model=CreateOrderResponse, status_code=201)
async def create_order(
    payload: CreateOrderRequest,
    ctx: AuthContext = Depends(require_role(*ROLE_CAN_MANAGE_BILLING)),
    db: AsyncSession = Depends(get_db),
) -> CreateOrderResponse:
    purchase, key_id = await service.create_order(
        db, organization_id=ctx.organization_id, plan_code=payload.plan_code
    )
    return CreateOrderResponse(
        order_id=purchase.provider_order_id,
        amount_minor=purchase.amount_minor,
        currency=purchase.currency,
        razorpay_key_id=key_id,
        purchase_id=purchase.id,
    )


@router.get("/billing/status", response_model=BillingStatusOut)
async def billing_status(
    ctx: AuthContext = Depends(require_role(*ROLE_CAN_MANAGE_BILLING)),
    db: AsyncSession = Depends(get_db),
) -> BillingStatusOut:
    from sqlalchemy import func, select

    from app.modules.entitlements.models import AuditEntitlement, EntitlementStatus, EntitlementType
    from app.modules.billing.models import Subscription, SubscriptionStatus

    has_sub = (
        await db.execute(
            select(func.count()).select_from(Subscription).where(
                Subscription.organization_id == ctx.organization_id,
                Subscription.status == SubscriptionStatus.ACTIVE.value,
            )
        )
    ).scalar_one() > 0

    credits = (
        await db.execute(
            select(func.coalesce(func.sum(AuditEntitlement.remaining), 0)).where(
                AuditEntitlement.organization_id == ctx.organization_id,
                AuditEntitlement.type.in_(
                    [EntitlementType.PURCHASED.value, EntitlementType.SUBSCRIPTION.value]
                ),
                AuditEntitlement.status.in_(
                    [EntitlementStatus.AVAILABLE.value, EntitlementStatus.RELEASED.value]
                ),
            )
        )
    ).scalar_one()

    return BillingStatusOut(has_active_subscription=has_sub, available_credits=int(credits))


@router.post("/webhooks/razorpay", status_code=200)
async def razorpay_webhook(
    request: Request,
    x_razorpay_signature: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """§13/§121 — idempotent, signature-verified. Always returns 200 once
    the signature checks out (even for an event type we don't act on), so
    Razorpay doesn't retry forever; a bad signature is the only rejection.
    """
    settings = get_settings()
    raw_body = await request.body()  # MUST read raw bytes before any parsing — signature covers this exact body

    if not x_razorpay_signature or not verify_webhook_signature(
        body=raw_body, signature=x_razorpay_signature, secret=settings.razorpay_webhook_secret
    ):
        raise UnauthenticatedError("Invalid webhook signature.")

    import json

    payload = json.loads(raw_body)
    event_type = payload.get("event", "unknown")
    provider_event_id = payload.get("id") or f"{event_type}:{hash(raw_body)}"

    is_new = await service.record_webhook_event(
        db, provider_event_id=provider_event_id, event_type=event_type, payload=payload
    )
    if not is_new:
        logger.info("webhook_duplicate_ignored", event_type=event_type, provider_event_id=provider_event_id)
        return {"status": "ok"}

    entity = payload.get("payload", {})
    if event_type == "payment.captured":
        payment = entity.get("payment", {}).get("entity", {})
        await service.process_payment_captured(db, order_id=payment.get("order_id"), payment_id=payment.get("id"))
    elif event_type == "payment.failed":
        payment = entity.get("payment", {}).get("entity", {})
        await service.process_payment_failed(db, order_id=payment.get("order_id"))
    # subscription.* events are schema-ready (Subscription model) but not
    # processed in M1 — the tested payment flow is the single-audit
    # purchase; recurring subscriptions ship in a later milestone.

    return {"status": "ok"}
