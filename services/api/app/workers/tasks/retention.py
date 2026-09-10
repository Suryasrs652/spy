"""§109 — daily purge of retention-expired data.

Never touches `Audit`, `AuditIssue`, or `Recommendation` rows (the durable
score history and issue *summaries* an account's audit trend is built on,
and what §133 comparison reads) — only the heavy per-page crawl detail
behind an old, finished audit, plus operational rows that are only ever
useful short-term (idempotency keys) or for a bounded compliance window
(admin audit logs).
"""
from __future__ import annotations

import asyncio
from datetime import timedelta

import structlog
from sqlalchemy import delete, select

from app.core.config import get_settings
from app.db.base import utcnow
from app.db.session import AsyncSessionLocal
from app.modules.admin.models import AuditLog, IdempotencyKey
from app.modules.audits.models import TERMINAL_STATUSES, Audit
from app.modules.crawler.models import CrawlPage
from app.workers.celery_app import celery_app

logger = structlog.get_logger(__name__)


async def _purge_stale_crawl_data(db, *, retention_days: int) -> int:
    cutoff = utcnow() - timedelta(days=retention_days)
    terminal_values = [s.value for s in TERMINAL_STATUSES]
    audit_ids = (
        await db.execute(select(Audit.id).where(Audit.created_at < cutoff, Audit.status.in_(terminal_values)))
    ).scalars().all()
    if not audit_ids:
        return 0
    # PageLink (source_page_id) and AuditIssuePage (page_id) both carry
    # ON DELETE CASCADE to crawl_pages, so this one delete is enough to
    # clean up every row that exists only to describe those pages.
    result = await db.execute(delete(CrawlPage).where(CrawlPage.audit_id.in_(audit_ids)))
    await db.commit()
    return result.rowcount or 0


async def _purge_stale_idempotency_keys(db, *, retention_days: int) -> int:
    cutoff = utcnow() - timedelta(days=retention_days)
    result = await db.execute(delete(IdempotencyKey).where(IdempotencyKey.created_at < cutoff))
    await db.commit()
    return result.rowcount or 0


async def _purge_stale_audit_logs(db, *, retention_days: int) -> int:
    cutoff = utcnow() - timedelta(days=retention_days)
    result = await db.execute(delete(AuditLog).where(AuditLog.created_at < cutoff))
    await db.commit()
    return result.rowcount or 0


async def run_retention_purge() -> dict:
    settings = get_settings()
    async with AsyncSessionLocal() as db:
        crawl_rows = await _purge_stale_crawl_data(db, retention_days=settings.crawl_data_retention_days)
        idempotency_rows = await _purge_stale_idempotency_keys(
            db, retention_days=settings.idempotency_key_retention_days
        )
        audit_log_rows = await _purge_stale_audit_logs(db, retention_days=settings.audit_log_retention_days)

    result = {
        "crawl_pages_deleted": crawl_rows,
        "idempotency_keys_deleted": idempotency_rows,
        "audit_logs_deleted": audit_log_rows,
    }
    logger.info("retention_purge_completed", **result)
    return result


@celery_app.task(name="app.workers.tasks.retention.purge_expired_data_task")
def purge_expired_data_task() -> dict:
    return asyncio.run(run_retention_purge())
