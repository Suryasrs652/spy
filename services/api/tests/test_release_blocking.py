"""§118-§123 — release-blocking tests. Every test in this file must pass
before Spy can ship (§150).

Requires a real Postgres + Redis + MinIO (docker compose up) — see the
module docstring in conftest.py for how these are wired.
"""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import uuid

import pytest
from sqlalchemy import select

from tests.conftest import unique_domain, unique_email, wait_for_audit_terminal


# ── §118: the full commercial loop ──────────────────────────────────────
@pytest.mark.asyncio
async def test_full_commercial_loop(client, db, auth_headers, monkeypatch):
    from app.core.config import get_settings
    from app.modules.audits.models import AuditStatus
    from app.modules.entitlements.models import EntitlementStatus

    # A real target the crawler can actually reach — kept to a single,
    # small, well-known page so this test doesn't depend on a specific
    # production site's content, only on it returning valid HTML.
    settings = get_settings()

    # 1. signup
    email = unique_email()
    signup_resp = await client.post(
        "/api/v1/auth/signup", json={"email": email, "password": "correct horse battery staple"}
    )
    assert signup_resp.status_code == 201
    org_id = signup_resp.json()["organization_id"]
    user_id = signup_resp.json()["user_id"]

    # 2. verify email directly via DB (bypassing the email round-trip)
    from app.modules.auth.models import User
    from datetime import datetime, timezone

    user = (await db.execute(select(User).where(User.id == uuid.UUID(user_id)))).scalar_one()
    user.email_verified_at = datetime.now(timezone.utc)
    await db.commit()

    from app.core.security import issue_access_token

    token = issue_access_token(user_id, org_id)
    headers = auth_headers(token, org_id)

    # 3. create project
    project_resp = await client.post(
        "/api/v1/projects", json={"name": "Test Site", "url": "https://example.com"}, headers=headers
    )
    assert project_resp.status_code == 201
    project_id = project_resp.json()["id"]

    # 4. entitlement check: free audit available
    ent_resp = await client.get("/api/v1/entitlements/audit", headers=headers)
    assert ent_resp.json()["can_run"] is True
    assert ent_resp.json()["type"] == "FREE_LIFETIME"

    # 5. run free audit
    audit_resp = await client.post("/api/v1/audits", json={"project_id": project_id}, headers=headers)
    assert audit_resp.status_code == 201
    audit_id = uuid.UUID(audit_resp.json()["id"])

    audit = await wait_for_audit_terminal(db, audit_id, timeout=60)
    assert audit.status == AuditStatus.COMPLETED.value, f"audit failed: {audit.failure_code} {audit.failure_message}"

    # 6. free entitlement now consumed
    from app.modules.entitlements.models import AuditEntitlement

    entitlement = (
        await db.execute(select(AuditEntitlement).where(AuditEntitlement.audit_id == audit_id))
    ).scalar_one()
    assert entitlement.status == EntitlementStatus.CONSUMED.value

    ent_resp2 = await client.get("/api/v1/entitlements/audit", headers=headers)
    assert ent_resp2.json()["can_run"] is False
    assert ent_resp2.json()["reason"] == "PAYMENT_REQUIRED"

    # 7. second audit -> 402
    second_audit_resp = await client.post("/api/v1/audits", json={"project_id": project_id}, headers=headers)
    assert second_audit_resp.status_code == 402
    assert second_audit_resp.json()["error"]["code"] == "AUDIT_PAYMENT_REQUIRED"

    # 8. buy a credit — create order, then simulate Razorpay's webhook
    monkeypatch.setattr(
        "app.modules.billing.service.razorpay_create_order",
        lambda **kw: {"id": f"order_{uuid.uuid4().hex[:16]}"},
    )
    order_resp = await client.post("/api/v1/billing/order", json={"plan_code": "SINGLE_AUDIT"}, headers=headers)
    assert order_resp.status_code == 201
    order_id = order_resp.json()["order_id"]

    payload = {
        "event": "payment.captured",
        "payload": {"payment": {"entity": {"id": f"pay_{uuid.uuid4().hex[:12]}", "order_id": order_id}}},
    }
    body = json.dumps(payload).encode()
    sig = hmac.new(settings.razorpay_webhook_secret.encode(), body, hashlib.sha256).hexdigest()

    webhook_resp = await client.post(
        "/api/v1/webhooks/razorpay", content=body,
        headers={"Content-Type": "application/json", "X-Razorpay-Signature": sig},
    )
    assert webhook_resp.status_code == 200

    # 9. credit granted
    status_resp = await client.get("/api/v1/billing/status", headers=headers)
    assert status_resp.json()["available_credits"] >= 1

    # 10. second audit now runs
    third_audit_resp = await client.post("/api/v1/audits", json={"project_id": project_id}, headers=headers)
    assert third_audit_resp.status_code == 201
    third_audit_id = uuid.UUID(third_audit_resp.json()["id"])
    third_audit = await wait_for_audit_terminal(db, third_audit_id, timeout=60)
    assert third_audit.status == AuditStatus.COMPLETED.value

    # 11. credit consumed
    from app.modules.billing.models import Purchase

    purchase = (await db.execute(select(Purchase).where(Purchase.provider_order_id == order_id))).scalar_one()
    credit = (
        await db.execute(
            select(AuditEntitlement).where(
                AuditEntitlement.audit_id == third_audit_id,
                AuditEntitlement.type == "PURCHASED",
            )
        )
    ).scalar_one()
    assert credit.status == EntitlementStatus.CONSUMED.value
    assert purchase.status == "PAID"


# ── §119: worker failure releases the free entitlement ──────────────────
@pytest.mark.asyncio
async def test_audit_worker_error_releases_entitlement(client, db, auth_headers, verified_user, monkeypatch):
    from app.modules.audits.models import AuditStatus
    from app.modules.entitlements.models import AuditEntitlement, EntitlementStatus

    user, org_id, token = verified_user
    headers = auth_headers(token, org_id)

    project_resp = await client.post(
        "/api/v1/projects", json={"name": "Will Fail", "url": "https://example.com"}, headers=headers
    )
    project_id = project_resp.json()["id"]

    async def _boom(*args, **kwargs):
        raise RuntimeError("simulated worker crash")

    monkeypatch.setattr("app.workers.tasks.crawl.crawl_site", _boom)

    audit_resp = await client.post("/api/v1/audits", json={"project_id": project_id}, headers=headers)
    audit_id = uuid.UUID(audit_resp.json()["id"])

    audit = await wait_for_audit_terminal(db, audit_id, timeout=30)
    assert audit.status == AuditStatus.FAILED.value
    assert audit.failure_code == "WORKER_ERROR"

    entitlement = (
        await db.execute(select(AuditEntitlement).where(AuditEntitlement.audit_id == audit_id))
    ).scalar_one()
    assert entitlement.status == EntitlementStatus.RELEASED.value

    # user can retry: a fresh audit request is allowed again
    retry_resp = await client.post("/api/v1/audits", json={"project_id": project_id}, headers=headers)
    assert retry_resp.status_code == 201


# ── §120: payment failure grants nothing ────────────────────────────────
@pytest.mark.asyncio
async def test_payment_failure_grants_no_entitlement(client, db, auth_headers, verified_user, monkeypatch):
    from app.core.config import get_settings

    user, org_id, token = verified_user
    headers = auth_headers(token, org_id)
    settings = get_settings()

    monkeypatch.setattr(
        "app.modules.billing.service.razorpay_create_order",
        lambda **kw: {"id": f"order_{uuid.uuid4().hex[:16]}"},
    )
    order_resp = await client.post("/api/v1/billing/order", json={"plan_code": "SINGLE_AUDIT"}, headers=headers)
    order_id = order_resp.json()["order_id"]

    payload = {"event": "payment.failed", "payload": {"payment": {"entity": {"order_id": order_id}}}}
    body = json.dumps(payload).encode()
    sig = hmac.new(settings.razorpay_webhook_secret.encode(), body, hashlib.sha256).hexdigest()

    resp = await client.post(
        "/api/v1/webhooks/razorpay", content=body,
        headers={"Content-Type": "application/json", "X-Razorpay-Signature": sig},
    )
    assert resp.status_code == 200

    status_resp = await client.get("/api/v1/billing/status", headers=headers)
    assert status_resp.json()["available_credits"] == 0

    from app.modules.billing.models import Purchase

    purchase = (await db.execute(select(Purchase).where(Purchase.provider_order_id == order_id))).scalar_one()
    assert purchase.status == "FAILED"


# ── §121: duplicate webhook grants exactly one credit ───────────────────
@pytest.mark.asyncio
async def test_duplicate_webhook_grants_exactly_one_credit(client, db, auth_headers, verified_user, monkeypatch):
    from app.core.config import get_settings
    from app.modules.entitlements.models import AuditEntitlement

    user, org_id, token = verified_user
    headers = auth_headers(token, org_id)
    settings = get_settings()

    monkeypatch.setattr(
        "app.modules.billing.service.razorpay_create_order",
        lambda **kw: {"id": f"order_{uuid.uuid4().hex[:16]}"},
    )
    order_resp = await client.post("/api/v1/billing/order", json={"plan_code": "SINGLE_AUDIT"}, headers=headers)
    order_id = order_resp.json()["order_id"]

    payload = {
        "id": f"evt_{uuid.uuid4().hex[:16]}",  # same Razorpay event id both times
        "event": "payment.captured",
        "payload": {"payment": {"entity": {"id": f"pay_{uuid.uuid4().hex[:12]}", "order_id": order_id}}},
    }
    body = json.dumps(payload).encode()
    sig = hmac.new(settings.razorpay_webhook_secret.encode(), body, hashlib.sha256).hexdigest()
    headers_wh = {"Content-Type": "application/json", "X-Razorpay-Signature": sig}

    resp1 = await client.post("/api/v1/webhooks/razorpay", content=body, headers=headers_wh)
    resp2 = await client.post("/api/v1/webhooks/razorpay", content=body, headers=headers_wh)
    assert resp1.status_code == 200
    assert resp2.status_code == 200  # duplicate is acknowledged, not processed twice

    from app.modules.billing.models import Purchase

    purchases = (
        await db.execute(select(Purchase).where(Purchase.provider_order_id == order_id))
    ).scalars().all()
    assert len(purchases) == 1
    assert purchases[0].status == "PAID"

    entitlements = (
        await db.execute(
            select(AuditEntitlement).where(
                AuditEntitlement.organization_id == uuid.UUID(str(org_id)),
                AuditEntitlement.type == "PURCHASED",
            )
        )
    ).scalars().all()
    assert len(entitlements) == 1, "duplicate webhook delivery must not create a second entitlement"


# ── §122: tenant isolation ───────────────────────────────────────────────
@pytest.mark.asyncio
async def test_cross_tenant_project_access_returns_404(client, auth_headers):
    from app.core.security import issue_access_token
    from app.modules.auth import service as auth_service

    # two independent, unrelated users/orgs
    async def _make_verified_user(db):
        from datetime import datetime, timezone

        email = unique_email()
        user, org_id = await auth_service.signup(db, email=email, password="correct horse battery staple", name=None)
        user.email_verified_at = datetime.now(timezone.utc)
        await db.commit()
        return user, org_id

    from app.db.session import AsyncSessionLocal

    async with AsyncSessionLocal() as db_a:
        user_a, org_a = await _make_verified_user(db_a)
    async with AsyncSessionLocal() as db_b:
        user_b, org_b = await _make_verified_user(db_b)

    token_a = issue_access_token(str(user_a.id), str(org_a))
    token_b = issue_access_token(str(user_b.id), str(org_b))

    headers_a = auth_headers(token_a, org_a)
    project_resp = await client.post(
        "/api/v1/projects", json={"name": "A's Project", "url": f"{unique_domain()}"}, headers=headers_a
    )
    assert project_resp.status_code == 201
    project_id = project_resp.json()["id"]

    # B tries to read A's project using B's own valid token/org
    headers_b = auth_headers(token_b, org_b)
    resp = await client.get(f"/api/v1/projects/{project_id}", headers=headers_b)
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "NOT_FOUND"

    # B cannot even use A's organization id with B's own token
    forged_headers = auth_headers(token_b, org_a)
    resp2 = await client.get(f"/api/v1/projects/{project_id}", headers=forged_headers)
    assert resp2.status_code == 404  # not a member of org_a -> looks like org_a doesn't exist


# ── §123: SSRF guard, end to end through the API ────────────────────────
@pytest.mark.asyncio
@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1/",
        "http://169.254.169.254/latest/meta-data/",
        "http://10.0.0.5/",
        "http://192.168.1.1/",
        "http://localhost/",
    ],
)
async def test_project_creation_blocks_ssrf_targets(client, auth_headers, verified_user, url):
    user, org_id, token = verified_user
    headers = auth_headers(token, org_id)
    resp = await client.post("/api/v1/projects", json={"name": "Evil", "url": url}, headers=headers)
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "BLOCKED_TARGET"


# ── Concurrency: 20 simultaneous free-audit attempts yield exactly one ──
@pytest.mark.asyncio
async def test_concurrent_free_audit_requests_yield_exactly_one(client, db, auth_headers, verified_user):
    from app.modules.entitlements.models import AuditEntitlement

    user, org_id, token = verified_user
    headers = auth_headers(token, org_id)

    project_resp = await client.post(
        "/api/v1/projects", json={"name": "Race", "url": unique_domain()}, headers=headers
    )
    project_id = project_resp.json()["id"]

    async def _attempt():
        try:
            return await client.post("/api/v1/audits", json={"project_id": project_id}, headers=headers)
        except Exception as exc:  # noqa: BLE001
            return exc

    results = await asyncio.gather(*[_attempt() for _ in range(20)])
    successes = [r for r in results if not isinstance(r, Exception) and r.status_code == 201]
    assert len(successes) == 1, f"expected exactly one successful audit creation, got {len(successes)}"

    entitlements = (
        await db.execute(
            select(AuditEntitlement).where(
                AuditEntitlement.organization_id == uuid.UUID(str(org_id)),
                AuditEntitlement.type == "FREE_LIFETIME",
            )
        )
    ).scalars().all()
    assert len(entitlements) == 1, "exactly one FREE_LIFETIME entitlement row must exist regardless of the race"
