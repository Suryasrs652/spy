"""§144/M5 — runs a competitor benchmark crawl (app/modules/competitors.
service.run_competitor_benchmark) as a background job, triggered by
`POST /projects/{id}/competitors/{id}/refresh`."""
from __future__ import annotations

import asyncio
import uuid

import structlog

from app.db.session import AsyncSessionLocal
from app.modules.competitors.service import run_competitor_benchmark
from app.workers.celery_app import celery_app

logger = structlog.get_logger(__name__)


async def _run_async(competitor_id: str) -> None:
    async with AsyncSessionLocal() as db:
        await run_competitor_benchmark(db, competitor_id=uuid.UUID(competitor_id))


@celery_app.task(name="app.workers.tasks.competitors.refresh_competitor_task", bind=True, max_retries=0)
def refresh_competitor_task(self, competitor_id: str) -> None:
    asyncio.run(_run_async(competitor_id))
