"""§92 GSC reporting endpoints' backing queries — plain aggregation over
already-synced `gsc_daily_metrics` rows, no live Google API calls (those
only happen during sync, §33)."""
from __future__ import annotations

import uuid
from datetime import date, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.gsc.models import GscDailyMetric


async def get_performance_summary(db: AsyncSession, *, property_id: uuid.UUID, days: int = 28) -> dict:
    end = date.today()
    start = end - timedelta(days=days)
    result = await db.execute(
        select(
            func.sum(GscDailyMetric.clicks),
            func.sum(GscDailyMetric.impressions),
            func.avg(GscDailyMetric.position),
        ).where(
            GscDailyMetric.property_id == property_id,
            GscDailyMetric.date >= start,
            GscDailyMetric.date <= end,
        )
    )
    clicks, impressions, position = result.one()
    clicks, impressions = int(clicks or 0), int(impressions or 0)
    return {
        "period": [start.isoformat(), end.isoformat()],
        "clicks": clicks,
        "impressions": impressions,
        "ctr": round(clicks / impressions, 4) if impressions else 0.0,
        "average_position": round(float(position or 0), 2),
        "source": "Google Search Console",
    }


async def get_top_queries(db: AsyncSession, *, property_id: uuid.UUID, days: int = 28, limit: int = 100) -> list[dict]:
    end = date.today()
    start = end - timedelta(days=days)
    result = await db.execute(
        select(
            GscDailyMetric.query,
            func.sum(GscDailyMetric.clicks),
            func.sum(GscDailyMetric.impressions),
            func.avg(GscDailyMetric.position),
        )
        .where(
            GscDailyMetric.property_id == property_id,
            GscDailyMetric.date >= start,
            GscDailyMetric.date <= end,
            GscDailyMetric.query.isnot(None),
        )
        .group_by(GscDailyMetric.query)
        .order_by(func.sum(GscDailyMetric.clicks).desc())
        .limit(limit)
    )
    return [
        {
            "query": row[0], "clicks": int(row[1] or 0), "impressions": int(row[2] or 0),
            "ctr": round(int(row[1] or 0) / int(row[2]), 4) if row[2] else 0.0,
            "position": round(float(row[3] or 0), 2),
        }
        for row in result.all()
    ]


async def get_top_pages(db: AsyncSession, *, property_id: uuid.UUID, days: int = 28, limit: int = 100) -> list[dict]:
    end = date.today()
    start = end - timedelta(days=days)
    result = await db.execute(
        select(
            GscDailyMetric.page,
            func.sum(GscDailyMetric.clicks),
            func.sum(GscDailyMetric.impressions),
            func.avg(GscDailyMetric.position),
        )
        .where(
            GscDailyMetric.property_id == property_id,
            GscDailyMetric.date >= start,
            GscDailyMetric.date <= end,
            GscDailyMetric.page.isnot(None),
        )
        .group_by(GscDailyMetric.page)
        .order_by(func.sum(GscDailyMetric.clicks).desc())
        .limit(limit)
    )
    return [
        {
            "page": row[0], "clicks": int(row[1] or 0), "impressions": int(row[2] or 0),
            "ctr": round(int(row[1] or 0) / int(row[2]), 4) if row[2] else 0.0,
            "position": round(float(row[3] or 0), 2),
        }
        for row in result.all()
    ]
