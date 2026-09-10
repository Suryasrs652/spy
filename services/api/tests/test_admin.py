"""§128/§129 admin dashboard — real session-based SUPER_ADMIN auth (not the
M1 shared-internal-token placeholder), plus the revenue/queue/error
dashboards, against real Postgres.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest

from app.core.security import issue_access_token


async def _make_super_admin(db, verified_user):
    user, org_id, _token = verified_user
    user.is_super_admin = True
    await db.commit()
    await db.refresh(user)
    admin_token = issue_access_token(str(user.id), str(org_id))
    return user, admin_token


@pytest.mark.asyncio
async def test_non_admin_user_is_forbidden(client, verified_user):
    _user, _org_id, token = verified_user
    resp = await client.get("/api/v1/admin/overview", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_missing_token_is_unauthenticated(client):
    resp = await client.get("/api/v1/admin/overview")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_super_admin_can_view_overview(client, db, verified_user):
    _user, token = await _make_super_admin(db, verified_user)
    resp = await client.get("/api/v1/admin/overview", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    body = resp.json()
    assert "registered_users" in body
    assert body["registered_users"] >= 1


@pytest.mark.asyncio
async def test_revenue_dashboard_reflects_paid_purchases(client, db, verified_user):
    from app.modules.billing.models import Purchase, PurchaseStatus

    admin_user, token = await _make_super_admin(db, verified_user)
    _u, org_id, _t = verified_user

    db.add(Purchase(
        organization_id=org_id, provider="razorpay", provider_order_id=f"order_{uuid.uuid4().hex[:10]}",
        product_type="SINGLE_AUDIT", amount_minor=49900, currency="INR",
        status=PurchaseStatus.PAID.value, paid_at=datetime.now(timezone.utc),
    ))
    await db.commit()

    resp = await client.get("/api/v1/admin/revenue", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["total_revenue_minor"] >= 49900
    assert body["total_paid_purchases"] >= 1
    assert any(row["product_type"] == "SINGLE_AUDIT" for row in body["revenue_by_product_type"])


@pytest.mark.asyncio
async def test_queue_dashboard_flags_stuck_jobs(client, db, verified_user):
    from app.modules.audits.models import Audit, AuditJob, AuditStatus
    from app.modules.projects.models import Project

    admin_user, token = await _make_super_admin(db, verified_user)
    user, org_id, _t = verified_user

    project = Project(organization_id=org_id, name="Stuck Site", domain="stuck.example", canonical_origin="https://stuck.example")
    db.add(project)
    await db.flush()

    audit = Audit(organization_id=org_id, project_id=project.id, requested_by=user.id, status=AuditStatus.CRAWLING.value)
    db.add(audit)
    await db.flush()

    stale_heartbeat = datetime.now(timezone.utc) - timedelta(minutes=30)
    db.add(AuditJob(audit_id=audit.id, status=AuditStatus.CRAWLING.value, heartbeat_at=stale_heartbeat))
    await db.commit()

    resp = await client.get("/api/v1/admin/queue", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    body = resp.json()
    assert any(j["audit_id"] == str(audit.id) for j in body["stuck_jobs"])


@pytest.mark.asyncio
async def test_error_dashboard_summarizes_failed_audits(client, db, verified_user):
    from app.modules.audits.models import Audit, AuditStatus, FailureCategory, FailureCode
    from app.modules.projects.models import Project

    admin_user, token = await _make_super_admin(db, verified_user)
    user, org_id, _t = verified_user

    project = Project(organization_id=org_id, name="Broken Site", domain="broken.example", canonical_origin="https://broken.example")
    db.add(project)
    await db.flush()

    db.add(Audit(
        organization_id=org_id, project_id=project.id, requested_by=user.id,
        status=AuditStatus.FAILED.value, failure_category=FailureCategory.TARGET_ERROR.value,
        failure_code=FailureCode.DNS_FAILURE.value,
    ))
    await db.commit()

    resp = await client.get("/api/v1/admin/errors", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["total_failed_audits"] >= 1
    assert any(row["failure_code"] == FailureCode.DNS_FAILURE.value for row in body["failures_by_code"])


@pytest.mark.asyncio
async def test_feature_flag_update_writes_audit_log(client, db, verified_user):
    admin_user, token = await _make_super_admin(db, verified_user)
    headers = {"Authorization": f"Bearer {token}"}

    resp = await client.patch("/api/v1/admin/feature-flags/GSC_ENABLED", params={"enabled": True}, headers=headers)
    assert resp.status_code == 200
    assert resp.json()["enabled"] is True

    logs_resp = await client.get("/api/v1/admin/audit-logs", headers=headers)
    assert logs_resp.status_code == 200
    logs = logs_resp.json()
    assert any(
        log["action"] == "feature_flag.update" and log["entity_id"] == "GSC_ENABLED" and log["user_id"] == str(admin_user.id)
        for log in logs
    )

    # Revert so this test doesn't leak state into others sharing the seeded flag.
    await client.patch("/api/v1/admin/feature-flags/GSC_ENABLED", params={"enabled": False}, headers=headers)
