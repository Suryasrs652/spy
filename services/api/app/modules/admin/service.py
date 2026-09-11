"""§129 — queue-health and error dashboards for the admin surface.

Every number here is a plain aggregation over rows that already exist for
other reasons (audit jobs, audits) — no separate analytics pipeline,
matching §3's "real data" principle applied to the admin surface itself.
"""
from __future__ import annotations

from datetime import timedelta

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import utcnow
from app.modules.admin.models import AuditLog
from app.modules.audits.models import TERMINAL_STATUSES, Audit, AuditJob, AuditStatus

# A running job whose heartbeat is older than this while not in a terminal
# state almost certainly means the worker that held it died mid-audit —
# heartbeat_at is refreshed on every crawl progress callback and on every
# _set_status transition (app/workers/tasks/crawl.py), so a multi-minute gap
# during a normal audit (which usually finishes in well under a minute) is
# a real anomaly, not a slow page.
STUCK_JOB_HEARTBEAT_THRESHOLD_MINUTES = 10


async def get_queue_health(db: AsyncSession) -> dict:
    status_counts = (
        await db.execute(select(AuditJob.status, func.count()).group_by(AuditJob.status))
    ).all()

    non_terminal = [s.value for s in AuditStatus if s not in TERMINAL_STATUSES]
    oldest_queued = (
        await db.execute(
            select(Audit.created_at)
            .join(AuditJob, AuditJob.audit_id == Audit.id)
            .where(AuditJob.status == AuditStatus.QUEUED.value)
            .order_by(Audit.created_at.asc())
            .limit(1)
        )
    ).scalar_one_or_none()

    stuck_cutoff = utcnow() - timedelta(minutes=STUCK_JOB_HEARTBEAT_THRESHOLD_MINUTES)
    stuck = (
        await db.execute(
            select(AuditJob.audit_id, AuditJob.status, AuditJob.heartbeat_at)
            .where(
                AuditJob.status.in_(non_terminal),
                (AuditJob.heartbeat_at.is_(None)) | (AuditJob.heartbeat_at < stuck_cutoff),
            )
        )
    ).all()

    now = utcnow()
    return {
        "jobs_by_status": {status: int(count) for status, count in status_counts},
        "oldest_queued_job_age_seconds": (
            int((now - oldest_queued).total_seconds()) if oldest_queued is not None else None
        ),
        "stuck_jobs": [
            {
                "audit_id": str(audit_id), "status": status,
                "heartbeat_age_seconds": int((now - heartbeat_at).total_seconds()) if heartbeat_at else None,
            }
            for audit_id, status, heartbeat_at in stuck
        ],
    }


async def get_error_summary(db: AsyncSession, *, days: int = 7) -> dict:
    since = utcnow() - timedelta(days=days)

    terminal_row = (
        await db.execute(
            select(
                func.count(),
                func.sum(case((Audit.status == AuditStatus.FAILED.value, 1), else_=0)),
            ).where(Audit.created_at >= since, Audit.status.in_([s.value for s in TERMINAL_STATUSES]))
        )
    ).one()
    total_terminal, total_failed = int(terminal_row[0] or 0), int(terminal_row[1] or 0)

    by_code = (
        await db.execute(
            select(Audit.failure_code, func.count())
            .where(Audit.status == AuditStatus.FAILED.value, Audit.created_at >= since)
            .group_by(Audit.failure_code)
            .order_by(func.count().desc())
        )
    ).all()
    by_category = (
        await db.execute(
            select(Audit.failure_category, func.count())
            .where(Audit.status == AuditStatus.FAILED.value, Audit.created_at >= since)
            .group_by(Audit.failure_category)
            .order_by(func.count().desc())
        )
    ).all()

    return {
        "days": days,
        "total_terminal_audits": total_terminal,
        "total_failed_audits": total_failed,
        "failure_rate": round(total_failed / total_terminal, 4) if total_terminal else None,
        "failures_by_code": [{"failure_code": c, "count": int(n)} for c, n in by_code],
        "failures_by_category": [{"failure_category": c, "count": int(n)} for c, n in by_category],
    }


async def list_audit_logs(db: AsyncSession, *, limit: int = 100, offset: int = 0) -> list[AuditLog]:
    result = await db.execute(
        select(AuditLog).order_by(AuditLog.created_at.desc()).limit(limit).offset(offset)
    )
    return list(result.scalars().all())
