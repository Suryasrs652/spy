from __future__ import annotations

import uuid

from pydantic import BaseModel, ConfigDict


class PlanOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    code: str
    name: str
    price_minor: int
    currency: str
    billing_interval: str
    audit_limit: int | None
    crawl_url_limit: int
    project_limit: int | None
    member_limit: int | None


class CreateOrderRequest(BaseModel):
    plan_code: str


class CreateOrderResponse(BaseModel):
    order_id: str
    amount_minor: int
    currency: str
    razorpay_key_id: str
    purchase_id: uuid.UUID


class BillingStatusOut(BaseModel):
    has_active_subscription: bool
    available_credits: int
