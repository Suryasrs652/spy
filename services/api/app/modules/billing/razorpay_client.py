"""Thin wrapper around the Razorpay SDK — the only place that library is
imported, so swapping/mocking it for tests means patching one module."""
from __future__ import annotations

from functools import lru_cache

import razorpay

from app.core.config import get_settings


@lru_cache
def get_client() -> razorpay.Client:
    settings = get_settings()
    client = razorpay.Client(auth=(settings.razorpay_key_id, settings.razorpay_key_secret))
    return client


def create_order(*, amount_minor: int, currency: str, receipt: str, notes: dict) -> dict:
    return get_client().order.create(
        {"amount": amount_minor, "currency": currency, "receipt": receipt, "notes": notes, "payment_capture": 1}
    )


def verify_webhook_signature(*, body: bytes, signature: str, secret: str) -> bool:
    try:
        get_client().utility.verify_webhook_signature(body.decode("utf-8"), signature, secret)
        return True
    except razorpay.errors.SignatureVerificationError:
        return False
