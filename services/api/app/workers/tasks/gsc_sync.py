"""§33 daily incremental GSC sync — scheduled via Celery Beat (see
celery_app.py's beat_schedule) and also triggerable on demand via
`POST /gsc/sync`.
"""
from __future__ import annotations

import asyncio

import structlog

from app.db.session import AsyncSessionLocal
from app.modules.gsc.sync_service import sync_all_selected_properties
from app.workers.celery_app import celery_app

logger = structlog.get_logger(__name__)


async def _sync_async() -> dict:
    async with AsyncSessionLocal() as db:
        return await sync_all_selected_properties(db)


@celery_app.task(name="app.workers.tasks.gsc_sync.daily_gsc_sync_task")
def daily_gsc_sync_task() -> dict:
    result = asyncio.run(_sync_async())
    logger.info("daily_gsc_sync_completed", **result)
    return result
