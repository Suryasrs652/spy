"""§144/M5 rank tracking — see models.py for why this is GSC-position-based
rather than a live SERP checker.
"""
from __future__ import annotations

import uuid
from datetime import date, timedelta

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ConflictError, NotFoundError
from app.modules.gsc.models import GscDailyMetric, GscProperty
from app.modules.keywords.models import TrackedKeyword

DEFAULT_HISTORY_DAYS = 90


async def add_tracked_keyword(
    db: AsyncSession, *, organization_id: uuid.UUID, project_id: uuid.UUID, keyword: str, user_id: uuid.UUID
) -> TrackedKeyword:
    tracked = TrackedKeyword(
        organization_id=organization_id, project_id=project_id,
        keyword=keyword.strip().lower(), added_by=user_id,
    )
    db.add(tracked)
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise ConflictError("This keyword is already being tracked for this project.") from exc
    await db.refresh(tracked)
    return tracked


async def list_tracked_keywords(db: AsyncSession, *, organization_id: uuid.UUID, project_id: uuid.UUID) -> list[TrackedKeyword]:
    result = await db.execute(
        select(TrackedKeyword)
        .where(TrackedKeyword.organization_id == organization_id, TrackedKeyword.project_id == project_id)
        .order_by(TrackedKeyword.created_at.desc())
    )
    return list(result.scalars().all())


async def remove_tracked_keyword(
    db: AsyncSession, *, organization_id: uuid.UUID, project_id: uuid.UUID, keyword_id: uuid.UUID
) -> None:
    tracked = (
        await db.execute(
            select(TrackedKeyword).where(
                TrackedKeyword.id == keyword_id,
                TrackedKeyword.organization_id == organization_id,
                TrackedKeyword.project_id == project_id,
            )
        )
    ).scalar_one_or_none()
    if tracked is None:
        raise NotFoundError("Tracked keyword not found.")
    await db.delete(tracked)
    await db.commit()


async def _selected_property_id(db: AsyncSession, *, project_id: uuid.UUID) -> uuid.UUID | None:
    result = await db.execute(
        select(GscProperty.id).where(GscProperty.project_id == project_id, GscProperty.selected.is_(True))
    )
    return result.scalar_one_or_none()


async def get_keyword_rank_history(
    db: AsyncSession, *, project_id: uuid.UUID, keyword: str, days: int = DEFAULT_HISTORY_DAYS
) -> dict:
    """Real GSC position history for one keyword, or an honest "no data"
    response — never a fabricated position (§3). No GSC property connected
    to this project, or no impressions for this keyword in the window,
    both produce `has_data: False` rather than guessing a rank.
    """
    property_id = await _selected_property_id(db, project_id=project_id)
    if property_id is None:
        return {"keyword": keyword, "has_data": False, "reason": "No Search Console property connected to this project.", "history": []}

    since = date.today() - timedelta(days=days)
    result = await db.execute(
        select(GscDailyMetric.date, GscDailyMetric.position, GscDailyMetric.clicks, GscDailyMetric.impressions)
        .where(
            GscDailyMetric.property_id == property_id,
            func.lower(GscDailyMetric.query) == keyword.strip().lower(),
            GscDailyMetric.date >= since,
        )
        .order_by(GscDailyMetric.date)
    )
    rows = result.all()
    if not rows:
        return {
            "keyword": keyword, "has_data": False,
            "reason": "No impressions recorded for this keyword in the synced Search Console data.",
            "history": [],
        }

    history = [
        {"date": d.isoformat(), "position": round(float(pos), 2), "clicks": clicks, "impressions": impressions}
        for d, pos, clicks, impressions in rows
    ]
    return {
        "keyword": keyword, "has_data": True,
        "current_position": history[-1]["position"],
        "best_position": min(h["position"] for h in history),
        "history": history,
    }


async def get_rank_overview(
    db: AsyncSession, *, organization_id: uuid.UUID, project_id: uuid.UUID, days: int = DEFAULT_HISTORY_DAYS
) -> list[dict]:
    """One summary row per tracked keyword — the list view; call
    get_keyword_rank_history for the full daily series behind one row.
    """
    tracked = await list_tracked_keywords(db, organization_id=organization_id, project_id=project_id)
    overview = []
    for kw in tracked:
        history = await get_keyword_rank_history(db, project_id=project_id, keyword=kw.keyword, days=days)
        overview.append({
            "id": kw.id, "keyword": kw.keyword, "added_at": kw.created_at,
            "has_data": history["has_data"],
            "current_position": history.get("current_position"),
            "best_position": history.get("best_position"),
        })
    return overview
