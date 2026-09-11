"""§128/§129 admin dashboard — the queue/error dashboards and feature
flags, against real Postgres.

The auth-gate tests (non-admin forbidden, missing token unauthenticated)
and the revenue dashboard are gone: Spy is self-hosted and single-user
with no billing, so the admin surface is simply open to whoever is
running the instance and there is no revenue to report.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest


@pytest.mark.asyncio
async def test_overview_is_reachable(client):
    resp = await client.get("/api/v1/admin/overview")
    assert resp.status_code == 200
    body = resp.json()
    assert "registered_users" in body
    assert "total_audits" in body


@pytest.mark.asyncio
async def test_queue_dashboard_flags_stuck_jobs(client, db, verified_user):
    from app.modules.audits.models import Audit, AuditJob, AuditStatus
    from app.modules.projects.models import Project

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

    resp = await client.get("/api/v1/admin/queue")
    assert resp.status_code == 200
    body = resp.json()
    assert any(j["audit_id"] == str(audit.id) for j in body["stuck_jobs"])


@pytest.mark.asyncio
async def test_error_dashboard_summarizes_failed_audits(client, db, verified_user):
    from app.modules.audits.models import Audit, AuditStatus, FailureCategory, FailureCode
    from app.modules.projects.models import Project

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

    resp = await client.get("/api/v1/admin/errors")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total_failed_audits"] >= 1
    assert any(row["failure_code"] == FailureCode.DNS_FAILURE.value for row in body["failures_by_code"])


@pytest.mark.asyncio
async def test_feature_flag_update_writes_audit_log(client, db, verified_user):
    user, _org_id, _t = verified_user

    resp = await client.patch("/api/v1/admin/feature-flags/GSC_ENABLED", params={"enabled": True})
    assert resp.status_code == 200
    assert resp.json()["enabled"] is True

    logs_resp = await client.get("/api/v1/admin/audit-logs")
    assert logs_resp.status_code == 200
    logs = logs_resp.json()
    assert any(
        log["action"] == "feature_flag.update" and log["entity_id"] == "GSC_ENABLED" and log["user_id"] == str(user.id)
        for log in logs
    )

    # Revert so this test doesn't leak state into others sharing the seeded flag.
    await client.patch("/api/v1/admin/feature-flags/GSC_ENABLED", params={"enabled": False})
