"""On-demand report (re)generation — the main pipeline (app.workers.tasks.
crawl) generates the report inline as its GENERATING_REPORT phase; this task
exists for regenerating a report later without re-running the whole audit
(e.g. after a report-template fix)."""
from __future__ import annotations

import asyncio
import uuid

import structlog
from sqlalchemy import select

from app.db.session import AsyncSessionLocal
from app.modules.audits.models import Audit
from app.modules.reports.service import generate_pdf_report
from app.workers.celery_app import celery_app

logger = structlog.get_logger(__name__)


async def _generate_async(audit_id: str) -> None:
    async with AsyncSessionLocal() as db:
        audit = (await db.execute(select(Audit).where(Audit.id == uuid.UUID(audit_id)))).scalar_one_or_none()
        if audit is None:
            logger.error("audit_not_found_for_report", audit_id=audit_id)
            return
        await generate_pdf_report(db, audit=audit)


@celery_app.task(name="app.workers.tasks.reports.generate_report_task")
def generate_report_task(audit_id: str) -> None:
    asyncio.run(_generate_async(audit_id))
