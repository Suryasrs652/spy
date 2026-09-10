"""§109 data retention — the daily purge job, run end-to-end against real
Postgres rows with backdated timestamps (no time-travel needed: the purge
only ever looks at `created_at`, so a row inserted "in the past" behaves
identically to one that actually aged there).

Every row's id/key is captured into a plain Python variable *before* the
commit that follows it — `AsyncSessionLocal` expires ORM objects on commit
(`expire_on_commit`), and touching an attribute on an expired object outside
an awaited call trips SQLAlchemy's async guard (MissingGreenlet); reading
plain variables afterward sidesteps that entirely.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.core.config import get_settings
from app.modules.admin.models import AuditLog, IdempotencyKey
from app.modules.audits.models import Audit, AuditStatus
from app.modules.crawler.models import CrawlPage
from app.modules.projects.models import Project
from app.workers.tasks.retention import run_retention_purge


def _days_ago(days: int) -> datetime:
    return datetime.now(timezone.utc) - timedelta(days=days)


@pytest.mark.asyncio
async def test_purge_removes_only_stale_crawl_pages(db, verified_user):
    settings = get_settings()
    user, org_id, _token = verified_user

    project = Project(organization_id=org_id, name="Retention Site", domain="retention.example", canonical_origin="https://retention.example")
    db.add(project)
    await db.flush()

    stale_audit = Audit(
        organization_id=org_id, project_id=project.id, requested_by=user.id,
        status=AuditStatus.COMPLETED.value, spy_score=80,
        created_at=_days_ago(settings.crawl_data_retention_days + 1),
    )
    fresh_audit = Audit(
        organization_id=org_id, project_id=project.id, requested_by=user.id,
        status=AuditStatus.COMPLETED.value, spy_score=80,
        created_at=_days_ago(1),
    )
    db.add_all([stale_audit, fresh_audit])
    await db.flush()
    stale_audit_id, fresh_audit_id = stale_audit.id, fresh_audit.id

    stale_page = CrawlPage(
        audit_id=stale_audit_id, project_id=project.id, url="https://retention.example/",
        normalized_url="https://retention.example/",
    )
    fresh_page = CrawlPage(
        audit_id=fresh_audit_id, project_id=project.id, url="https://retention.example/",
        normalized_url="https://retention.example/",
    )
    db.add_all([stale_page, fresh_page])
    await db.flush()
    stale_page_id, fresh_page_id = stale_page.id, fresh_page.id
    await db.commit()

    result = await run_retention_purge()
    assert result["crawl_pages_deleted"] >= 1

    remaining_stale = (await db.execute(select(CrawlPage).where(CrawlPage.id == stale_page_id))).scalar_one_or_none()
    remaining_fresh = (await db.execute(select(CrawlPage).where(CrawlPage.id == fresh_page_id))).scalar_one_or_none()
    assert remaining_stale is None, "crawl data past the retention window must be purged"
    assert remaining_fresh is not None, "recent crawl data must survive the purge"

    # The audit row itself (scores/evidence) is never purged — only the
    # heavy per-page detail behind it.
    still_there = (await db.execute(select(Audit).where(Audit.id == stale_audit_id))).scalar_one_or_none()
    assert still_there is not None


@pytest.mark.asyncio
async def test_purge_removes_only_stale_idempotency_keys(db, verified_user):
    settings = get_settings()
    _user, org_id, _token = verified_user

    stale_key_value = f"stale-{uuid.uuid4().hex}"
    fresh_key_value = f"fresh-{uuid.uuid4().hex}"
    db.add_all([
        IdempotencyKey(
            key=stale_key_value, organization_id=org_id, endpoint="POST /audits",
            response_status=201, response_body={}, created_at=_days_ago(settings.idempotency_key_retention_days + 1),
        ),
        IdempotencyKey(
            key=fresh_key_value, organization_id=org_id, endpoint="POST /audits",
            response_status=201, response_body={}, created_at=_days_ago(0),
        ),
    ])
    await db.commit()

    result = await run_retention_purge()
    assert result["idempotency_keys_deleted"] >= 1

    remaining_stale = (await db.execute(select(IdempotencyKey).where(IdempotencyKey.key == stale_key_value))).scalar_one_or_none()
    remaining_fresh = (await db.execute(select(IdempotencyKey).where(IdempotencyKey.key == fresh_key_value))).scalar_one_or_none()
    assert remaining_stale is None
    assert remaining_fresh is not None


@pytest.mark.asyncio
async def test_purge_removes_only_stale_audit_logs(db, verified_user):
    settings = get_settings()
    _user, org_id, _token = verified_user

    stale_log = AuditLog(
        organization_id=org_id, user_id=None, action="feature_flag.update",
        entity_type="feature_flag", entity_id="TEST_FLAG",
        created_at=_days_ago(settings.audit_log_retention_days + 1),
    )
    fresh_log = AuditLog(
        organization_id=org_id, user_id=None, action="feature_flag.update",
        entity_type="feature_flag", entity_id="TEST_FLAG",
        created_at=_days_ago(0),
    )
    db.add_all([stale_log, fresh_log])
    await db.flush()
    stale_id, fresh_id = stale_log.id, fresh_log.id
    await db.commit()

    result = await run_retention_purge()
    assert result["audit_logs_deleted"] >= 1

    remaining_stale = (await db.execute(select(AuditLog).where(AuditLog.id == stale_id))).scalar_one_or_none()
    remaining_fresh = (await db.execute(select(AuditLog).where(AuditLog.id == fresh_id))).scalar_one_or_none()
    assert remaining_stale is None
    assert remaining_fresh is not None
