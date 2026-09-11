"""Super admins get ADMIN_DAILY_FREE_AUDITS free audits per UTC calendar
day (a dogfooding/ops convenience) instead of the consumer FREE_LIFETIME
entitlement — see app/modules/entitlements/service.py.
"""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select

from tests.conftest import unique_domain, wait_for_audit_terminal


@pytest.mark.asyncio
async def test_super_admin_runs_two_real_audits_then_third_is_blocked(client, db, auth_headers, verified_user):
    """End-to-end through the real create-audit path (not seeded rows) —
    this is the regression test for a real off-by-one bug: the daily-cap
    check used to run *after* the current request's own Audit row was
    already flushed, so that not-yet-committed row counted against its
    own request and the effective cap was 1, not 2.
    """
    from app.modules.audits.models import AuditStatus
    from app.modules.entitlements.models import AuditEntitlement

    user, org_id, token = verified_user
    user.is_super_admin = True
    await db.commit()
    user_id = user.id  # captured now — `user` expires across the real crawls below
    headers = auth_headers(token, org_id)

    project_resp = await client.post(
        "/api/v1/projects", json={"name": "Admin E2E Test", "url": "https://example.com"}, headers=headers
    )
    project_id = project_resp.json()["id"]

    # First audit: full allowance available.
    ent_resp = await client.get("/api/v1/entitlements/audit", headers=headers)
    assert ent_resp.json() == {"can_run": True, "type": "ADMIN_DAILY_FREE", "remaining": 2, "reason": None}

    first_resp = await client.post("/api/v1/audits", json={"project_id": project_id}, headers=headers)
    assert first_resp.status_code == 201
    first_audit = await wait_for_audit_terminal(db, uuid.UUID(first_resp.json()["id"]), timeout=60)
    assert first_audit.status == AuditStatus.COMPLETED.value

    # Second audit on the same UTC day must still succeed — this is the
    # exact request that used to be wrongly rejected.
    ent_resp2 = await client.get("/api/v1/entitlements/audit", headers=headers)
    assert ent_resp2.json() == {"can_run": True, "type": "ADMIN_DAILY_FREE", "remaining": 1, "reason": None}

    second_resp = await client.post("/api/v1/audits", json={"project_id": project_id}, headers=headers)
    assert second_resp.status_code == 201, second_resp.json()
    second_audit = await wait_for_audit_terminal(db, uuid.UUID(second_resp.json()["id"]), timeout=60)
    assert second_audit.status == AuditStatus.COMPLETED.value

    # Third audit today is correctly blocked.
    ent_resp3 = await client.get("/api/v1/entitlements/audit", headers=headers)
    assert ent_resp3.json() == {"can_run": False, "type": None, "remaining": 0, "reason": "ADMIN_DAILY_LIMIT_REACHED"}

    third_resp = await client.post("/api/v1/audits", json={"project_id": project_id}, headers=headers)
    assert third_resp.status_code == 429
    assert third_resp.json()["error"]["code"] == "ADMIN_DAILY_LIMIT_REACHED"

    # Exactly two ADMIN_DAILY_FREE entitlements were ever created — no
    # FREE_LIFETIME row, and no extra rows from the blocked third attempt.
    entitlements = (
        await db.execute(
            select(AuditEntitlement).where(AuditEntitlement.user_id == user_id)
        )
    ).scalars().all()
    assert {e.type for e in entitlements} == {"ADMIN_DAILY_FREE"}
    assert len(entitlements) == 2


@pytest.mark.asyncio
async def test_super_admin_gets_two_free_audits_then_blocked(client, db, auth_headers, verified_user):
    from app.modules.audits.models import Audit, AuditStatus
    from app.modules.entitlements.models import AuditEntitlement, EntitlementStatus

    user, org_id, token = verified_user
    user.is_super_admin = True
    await db.commit()
    headers = auth_headers(token, org_id)

    project_resp = await client.post(
        "/api/v1/projects", json={"name": "Admin Test", "url": unique_domain()}, headers=headers
    )
    project_id = project_resp.json()["id"]

    # Fresh admin: entitlement status reports the full daily allowance,
    # never the one-time FREE_LIFETIME lane.
    ent_resp = await client.get("/api/v1/entitlements/audit", headers=headers)
    assert ent_resp.json() == {"can_run": True, "type": "ADMIN_DAILY_FREE", "remaining": 2, "reason": None}

    # Directly seed two already-"used today" entitlements rather than
    # running two real crawls — this test is about the entitlement/quota
    # bookkeeping, not the crawler (see the E2E test above for that).
    for _ in range(2):
        audit = Audit(
            organization_id=uuid.UUID(str(org_id)), project_id=uuid.UUID(project_id),
            requested_by=user.id, status=AuditStatus.COMPLETED.value,
        )
        db.add(audit)
        await db.flush()
        db.add(
            AuditEntitlement(
                organization_id=uuid.UUID(str(org_id)), user_id=user.id,
                type="ADMIN_DAILY_FREE", status=EntitlementStatus.CONSUMED.value,
                audit_id=audit.id, quantity=1, remaining=0, source="SUPER_ADMIN_DAILY_FREE",
            )
        )
    await db.commit()

    ent_resp2 = await client.get("/api/v1/entitlements/audit", headers=headers)
    assert ent_resp2.json() == {"can_run": False, "type": None, "remaining": 0, "reason": "ADMIN_DAILY_LIMIT_REACHED"}

    blocked_resp = await client.post("/api/v1/audits", json={"project_id": project_id}, headers=headers)
    assert blocked_resp.status_code == 429
    assert blocked_resp.json()["error"]["code"] == "ADMIN_DAILY_LIMIT_REACHED"

    # No FREE_LIFETIME row was ever created for this admin.
    free_lifetime = (
        await db.execute(
            select(AuditEntitlement).where(
                AuditEntitlement.user_id == user.id, AuditEntitlement.type == "FREE_LIFETIME"
            )
        )
    ).scalars().all()
    assert free_lifetime == []


@pytest.mark.asyncio
async def test_super_admin_released_admin_grant_does_not_count_against_daily_cap(client, db, auth_headers, verified_user):
    from app.modules.audits.models import Audit, AuditStatus
    from app.modules.entitlements.models import AuditEntitlement, EntitlementStatus

    user, org_id, token = verified_user
    user.is_super_admin = True
    await db.commit()
    headers = auth_headers(token, org_id)

    project_resp = await client.post(
        "/api/v1/projects", json={"name": "Admin Retry Test", "url": unique_domain()}, headers=headers
    )
    project_id = project_resp.json()["id"]

    # Two FAILED audits today, each with its ADMIN_DAILY_FREE entitlement
    # RELEASED (exactly what release_entitlement_for_audit does on
    # failure) — shouldn't burn the daily allowance, the same "release on
    # failure" fairness the consumer FREE_LIFETIME lane gets.
    for _ in range(2):
        audit = Audit(
            organization_id=uuid.UUID(str(org_id)), project_id=uuid.UUID(project_id),
            requested_by=user.id, status=AuditStatus.FAILED.value,
        )
        db.add(audit)
        await db.flush()
        db.add(
            AuditEntitlement(
                organization_id=uuid.UUID(str(org_id)), user_id=user.id,
                type="ADMIN_DAILY_FREE", status=EntitlementStatus.RELEASED.value,
                audit_id=audit.id, quantity=1, remaining=1, source="SUPER_ADMIN_DAILY_FREE",
            )
        )
    await db.commit()

    ent_resp = await client.get("/api/v1/entitlements/audit", headers=headers)
    assert ent_resp.json() == {"can_run": True, "type": "ADMIN_DAILY_FREE", "remaining": 2, "reason": None}
