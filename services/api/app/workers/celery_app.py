"""§101 queue architecture."""
from __future__ import annotations

from celery import Celery
from celery.schedules import crontab

from app.core.config import get_settings

settings = get_settings()

celery_app = Celery(
    "spy",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
    include=[
        "app.workers.tasks.crawl",
        "app.workers.tasks.reports",
        "app.workers.tasks.gsc_sync",
        "app.workers.tasks.retention",
        "app.workers.tasks.competitors",
    ],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_acks_late=True,
    broker_connection_retry_on_startup=True,
    worker_prefetch_multiplier=1,
    task_routes={
        "app.workers.tasks.crawl.run_audit_task": {"queue": "audit.standard"},
        "app.workers.tasks.reports.generate_report_task": {"queue": "reports"},
        "app.workers.tasks.gsc_sync.daily_gsc_sync_task": {"queue": "gsc"},
        "app.workers.tasks.retention.purge_expired_data_task": {"queue": "maintenance"},
        "app.workers.tasks.competitors.refresh_competitor_task": {"queue": "crawl"},
    },
    task_default_queue="audit.standard",
    beat_schedule={
        # §33 "1-day incremental pulls" — run once daily, well after Google's
        # own data settles (GSC_DATA_LAG_DAYS in sync_service.py already
        # backs off the sync window itself; this just picks a quiet hour).
        "daily-gsc-sync": {
            "task": "app.workers.tasks.gsc_sync.daily_gsc_sync_task",
            "schedule": crontab(hour=3, minute=0),
        },
        # §109 — daily retention purge, run at a different quiet hour than
        # the GSC sync so the two don't compete for DB write throughput.
        "daily-retention-purge": {
            "task": "app.workers.tasks.retention.purge_expired_data_task",
            "schedule": crontab(hour=4, minute=0),
        },
    },
)
