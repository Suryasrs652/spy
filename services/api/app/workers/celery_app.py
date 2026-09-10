"""§101 queue architecture."""
from __future__ import annotations

from celery import Celery

from app.core.config import get_settings

settings = get_settings()

celery_app = Celery(
    "spy",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
    include=[
        "app.workers.tasks.crawl",
        "app.workers.tasks.reports",
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
    },
    task_default_queue="audit.standard",
)
