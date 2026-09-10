"""§34 GSC opportunity engine — turns raw Search Console rows into
actionable findings. Every number here is computed straight from Google's
own first-party data (§142 data-source labeling: "source": "Google Search
Console"); the one estimate this module introduces (an expected-CTR curve
for the low-CTR check) is explicitly labeled "Spy Expected CTR", never
attributed to Google (§35).
"""
from __future__ import annotations

import uuid
from datetime import date, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.gsc.models import GscDailyMetric

# A rough, widely-cited organic CTR-by-position curve — used only as a
# baseline to flag queries performing well below "typical" for their
# position, not presented as ground truth (§35).
_SPY_EXPECTED_CTR_BY_POSITION = {
    1: 0.28, 2: 0.15, 3: 0.11, 4: 0.08, 5: 0.06,
    6: 0.05, 7: 0.04, 8: 0.03, 9: 0.03, 10: 0.02,
}
_DEFAULT_EXPECTED_CTR = 0.01

STRIKING_DISTANCE_MIN_POSITION = 4
STRIKING_DISTANCE_MAX_POSITION = 20
MIN_IMPRESSIONS_FOR_OPPORTUNITY = 10


def _expected_ctr(position: float) -> float:
    bucket = min(10, max(1, round(position)))
    return _SPY_EXPECTED_CTR_BY_POSITION.get(bucket, _DEFAULT_EXPECTED_CTR)


async def _aggregate_by(
    db: AsyncSession, *, property_id: uuid.UUID, dimension: str, start: date, end: date
) -> dict[str, dict]:
    column = GscDailyMetric.query if dimension == "query" else GscDailyMetric.page
    result = await db.execute(
        select(
            column,
            func.sum(GscDailyMetric.clicks),
            func.sum(GscDailyMetric.impressions),
            func.avg(GscDailyMetric.position),
        )
        .where(
            GscDailyMetric.property_id == property_id,
            GscDailyMetric.date >= start,
            GscDailyMetric.date <= end,
            column.isnot(None),
        )
        .group_by(column)
    )
    return {
        row[0]: {"clicks": int(row[1] or 0), "impressions": int(row[2] or 0), "position": float(row[3] or 0)}
        for row in result.all()
    }


async def get_search_opportunities(
    db: AsyncSession, *, property_id: uuid.UUID, as_of: date | None = None
) -> dict:
    """§34 — compares the last 28 days against the previous 28 days for
    declines/gains, and looks at the last 28 days alone for striking-
    distance / low-CTR / cannibalization / zero-click opportunities.
    """
    as_of = as_of or date.today()
    current_start, current_end = as_of - timedelta(days=28), as_of
    previous_start, previous_end = as_of - timedelta(days=56), as_of - timedelta(days=29)

    current_queries = await _aggregate_by(db, property_id=property_id, dimension="query", start=current_start, end=current_end)
    previous_queries = await _aggregate_by(db, property_id=property_id, dimension="query", start=previous_start, end=previous_end)
    current_pages = await _aggregate_by(db, property_id=property_id, dimension="page", start=current_start, end=current_end)
    previous_pages = await _aggregate_by(db, property_id=property_id, dimension="page", start=previous_start, end=previous_end)

    striking_distance = sorted(
        [
            {"query": q, **stats}
            for q, stats in current_queries.items()
            if STRIKING_DISTANCE_MIN_POSITION <= stats["position"] <= STRIKING_DISTANCE_MAX_POSITION
            and stats["impressions"] >= MIN_IMPRESSIONS_FOR_OPPORTUNITY
        ],
        key=lambda r: -r["impressions"],
    )[:50]

    low_ctr = []
    for q, stats in current_queries.items():
        if stats["impressions"] < MIN_IMPRESSIONS_FOR_OPPORTUNITY:
            continue
        actual_ctr = stats["clicks"] / stats["impressions"] if stats["impressions"] else 0
        expected = _expected_ctr(stats["position"])
        if actual_ctr < expected * 0.5:  # meaningfully underperforming, not just noise
            low_ctr.append({
                "query": q, **stats, "actual_ctr": round(actual_ctr, 4),
                "spy_expected_ctr": expected,
            })
    low_ctr.sort(key=lambda r: -r["impressions"])
    low_ctr = low_ctr[:50]

    high_impressions_no_clicks = sorted(
        [
            {"query": q, **stats}
            for q, stats in current_queries.items()
            if stats["clicks"] == 0 and stats["impressions"] >= MIN_IMPRESSIONS_FOR_OPPORTUNITY
        ],
        key=lambda r: -r["impressions"],
    )[:50]

    declining_queries = _period_over_period(current_queries, previous_queries, "query", declining=True)
    rising_queries = _period_over_period(current_queries, previous_queries, "query", declining=False)
    declining_pages = _period_over_period(current_pages, previous_pages, "page", declining=True)
    rising_pages = _period_over_period(current_pages, previous_pages, "page", declining=False)

    position_gains = _position_change(current_queries, previous_queries, improved=True)
    position_losses = _position_change(current_queries, previous_queries, improved=False)

    cannibalization = await _find_cannibalization(db, property_id=property_id, start=current_start, end=current_end)

    return {
        "period": {"current": [current_start.isoformat(), current_end.isoformat()],
                    "previous": [previous_start.isoformat(), previous_end.isoformat()]},
        "striking_distance_keywords": striking_distance,
        "low_ctr_opportunities": low_ctr,
        "high_impressions_no_clicks": high_impressions_no_clicks,
        "declining_keywords": declining_queries,
        "rising_keywords": rising_queries,
        "declining_pages": declining_pages,
        "rising_pages": rising_pages,
        "position_gains": position_gains,
        "position_losses": position_losses,
        "keyword_cannibalization": cannibalization,
    }


def _period_over_period(current: dict, previous: dict, key_name: str, *, declining: bool) -> list[dict]:
    changes = []
    for key, cur in current.items():
        prev = previous.get(key)
        if prev is None or prev["clicks"] < MIN_IMPRESSIONS_FOR_OPPORTUNITY:
            continue
        delta = cur["clicks"] - prev["clicks"]
        pct_change = delta / prev["clicks"] if prev["clicks"] else 0
        if (declining and delta < 0) or (not declining and delta > 0):
            changes.append({
                key_name: key, "current_clicks": cur["clicks"], "previous_clicks": prev["clicks"],
                "delta": delta, "pct_change": round(pct_change, 3),
            })
    changes.sort(key=lambda r: r["delta"] if declining else -r["delta"])
    return changes[:50]


def _position_change(current: dict, previous: dict, *, improved: bool) -> list[dict]:
    changes = []
    for query, cur in current.items():
        prev = previous.get(query)
        if prev is None or prev["impressions"] < MIN_IMPRESSIONS_FOR_OPPORTUNITY:
            continue
        delta = prev["position"] - cur["position"]  # positive = moved up (better)
        if (improved and delta > 0.5) or (not improved and delta < -0.5):
            changes.append({
                "query": query, "current_position": round(cur["position"], 1),
                "previous_position": round(prev["position"], 1), "delta": round(delta, 1),
            })
    changes.sort(key=lambda r: -abs(r["delta"]))
    return changes[:50]


async def _find_cannibalization(db: AsyncSession, *, property_id: uuid.UUID, start: date, end: date) -> list[dict]:
    result = await db.execute(
        select(
            GscDailyMetric.query,
            GscDailyMetric.page,
            func.sum(GscDailyMetric.clicks),
            func.sum(GscDailyMetric.impressions),
        )
        .where(
            GscDailyMetric.property_id == property_id,
            GscDailyMetric.date >= start,
            GscDailyMetric.date <= end,
            GscDailyMetric.query.isnot(None),
            GscDailyMetric.page.isnot(None),
        )
        .group_by(GscDailyMetric.query, GscDailyMetric.page)
        .having(func.sum(GscDailyMetric.impressions) >= MIN_IMPRESSIONS_FOR_OPPORTUNITY)
    )

    by_query: dict[str, list[dict]] = {}
    for query, page, clicks, impressions in result.all():
        by_query.setdefault(query, []).append({"page": page, "clicks": int(clicks or 0), "impressions": int(impressions or 0)})

    cannibalized = [
        {"query": q, "competing_pages": sorted(pages, key=lambda p: -p["impressions"])}
        for q, pages in by_query.items()
        if len(pages) > 1
    ]
    cannibalized.sort(key=lambda r: -sum(p["impressions"] for p in r["competing_pages"]))
    return cannibalized[:30]
