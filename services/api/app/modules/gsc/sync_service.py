"""§32-§33 GSC sync — initial 16-month backfill, then a rolling incremental
re-sync window.

Google's performance data for a given day can still be revised for a few
days after it first appears (§33) — rather than pull only "yesterday" on
each run, every incremental sync re-pulls a short rolling window so any
late corrections get picked up, and the delete-then-insert pattern below
makes that safe to run repeatedly (a re-synced day fully replaces the
previous version of that day, never duplicates it).
"""
from __future__ import annotations

import uuid
from datetime import date, timedelta

import structlog
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import utcnow
from app.modules.gsc.analytics_client import query_search_analytics, refresh_access_token
from app.modules.gsc.models import GscConnection, GscDailyMetric, GscProperty

logger = structlog.get_logger(__name__)

INITIAL_BACKFILL_DAYS = 16 * 30  # §33 "previous 16 months where available"
INCREMENTAL_WINDOW_DAYS = 5  # rolling re-sync window to catch Google's late data revisions
GSC_DATA_LAG_DAYS = 2  # §33 "performance data is typically available after a delay"

_DIMENSIONS = ["date", "query", "page", "country", "device"]


async def _has_any_data(db: AsyncSession, property_id: uuid.UUID) -> bool:
    result = await db.execute(
        select(GscDailyMetric.id).where(GscDailyMetric.property_id == property_id).limit(1)
    )
    return result.first() is not None


def _sync_date_range(is_first_sync: bool) -> tuple[date, date]:
    end = date.today() - timedelta(days=GSC_DATA_LAG_DAYS)
    if is_first_sync:
        start = end - timedelta(days=INITIAL_BACKFILL_DAYS)
    else:
        start = end - timedelta(days=INCREMENTAL_WINDOW_DAYS)
    return start, end


async def sync_property(db: AsyncSession, *, prop: GscProperty, connection: GscConnection) -> int:
    """Returns the number of rows written. Raises on API/token failure —
    callers (the Celery task) log and move on to the next property rather
    than letting one broken connection abort the whole sync run.
    """
    access_token = await refresh_access_token(connection.encrypted_refresh_token)

    is_first_sync = not await _has_any_data(db, prop.id)
    start_date, end_date = _sync_date_range(is_first_sync)

    rows = await query_search_analytics(
        access_token=access_token,
        site_url=prop.site_url,
        start_date=start_date.isoformat(),
        end_date=end_date.isoformat(),
        dimensions=_DIMENSIONS,
    )

    # Idempotent re-sync: fully replace this date range for this property
    # rather than trying to upsert row-by-row against Google's arbitrary
    # per-row ordering.
    await db.execute(
        delete(GscDailyMetric).where(
            GscDailyMetric.property_id == prop.id,
            GscDailyMetric.date >= start_date,
            GscDailyMetric.date <= end_date,
        )
    )

    metric_rows = []
    for row in rows:
        keys = row.get("keys", [])
        if len(keys) != len(_DIMENSIONS):
            continue
        values = dict(zip(_DIMENSIONS, keys))
        metric_rows.append(
            GscDailyMetric(
                property_id=prop.id,
                date=date.fromisoformat(values["date"]),
                query=values["query"] or None,
                page=values["page"] or None,
                country=values["country"] or None,
                device=values["device"] or None,
                search_type="web",
                clicks=int(row.get("clicks", 0)),
                impressions=int(row.get("impressions", 0)),
                ctr=round(float(row.get("ctr", 0.0)), 4),
                position=round(float(row.get("position", 0.0)), 2),
            )
        )

    if metric_rows:
        db.add_all(metric_rows)

    connection.last_sync_at = utcnow()
    await db.commit()

    logger.info(
        "gsc_property_synced", property_id=str(prop.id), site_url=prop.site_url,
        rows=len(metric_rows), first_sync=is_first_sync, start_date=str(start_date), end_date=str(end_date),
    )
    return len(metric_rows)


async def sync_all_selected_properties(db: AsyncSession) -> dict:
    """Iterates every selected property on every active connection —
    called by the daily Celery Beat task (§33) and by the manual
    `POST /gsc/sync` endpoint.
    """
    from app.modules.gsc.models import GscConnectionStatus

    result = await db.execute(
        select(GscProperty, GscConnection)
        .join(GscConnection, GscConnection.id == GscProperty.connection_id)
        .where(GscProperty.selected.is_(True), GscConnection.status == GscConnectionStatus.ACTIVE.value)
    )
    pairs = result.all()

    synced, failed = 0, 0
    for prop, connection in pairs:
        try:
            await sync_property(db, prop=prop, connection=connection)
            synced += 1
        except Exception:  # noqa: BLE001 - one broken connection shouldn't abort the whole run
            logger.error("gsc_sync_failed", property_id=str(prop.id), exc_info=True)
            failed += 1

    return {"synced": synced, "failed": failed, "total": len(pairs)}
