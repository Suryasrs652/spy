"""§34 GSC opportunity engine — real aggregation queries against real
Postgres rows (not mocked), since the whole point is verifying the SQL
grouping/threshold logic is correct.
"""
from __future__ import annotations

from datetime import date, timedelta

import pytest

from app.modules.gsc.models import GscConnection, GscConnectionStatus, GscProperty
from app.modules.gsc.opportunities import get_search_opportunities
from tests.conftest import unique_email


async def _make_property(db) -> GscProperty:
    from app.modules.auth import service as auth_service

    email = unique_email()
    user, org_id = await auth_service.signup(db, email=email, password="correct horse battery staple", name=None)

    connection = GscConnection(
        organization_id=org_id, user_id=user.id, google_account_id="test-account",
        encrypted_refresh_token="unused-in-this-test", scopes=[], status=GscConnectionStatus.ACTIVE.value,
    )
    db.add(connection)
    await db.flush()

    prop = GscProperty(connection_id=connection.id, site_url="https://example.com/", permission_level="siteOwner", selected=True)
    db.add(prop)
    await db.commit()
    await db.refresh(prop)
    return prop


def _metric(property_id, day, query, page, clicks, impressions, position):
    from app.modules.gsc.models import GscDailyMetric

    ctr = clicks / impressions if impressions else 0
    return GscDailyMetric(
        property_id=property_id, date=day, query=query, page=page, country="usa", device="DESKTOP",
        search_type="web", clicks=clicks, impressions=impressions, ctr=round(ctr, 4), position=position,
    )


@pytest.mark.asyncio
async def test_striking_distance_and_low_ctr(db):
    prop = await _make_property(db)
    today = date.today()

    # A query sitting at position 8 with real impressions -> striking distance.
    db.add(_metric(prop.id, today - timedelta(days=5), "buy widgets online", "/widgets", clicks=5, impressions=500, position=8.2))
    # A query ranking #2 but with almost no clicks relative to its position -> low CTR opportunity.
    db.add(_metric(prop.id, today - timedelta(days=5), "widget reviews", "/reviews", clicks=2, impressions=1000, position=2.0))
    # A normal, healthy query — should not appear in either list.
    db.add(_metric(prop.id, today - timedelta(days=5), "widget pricing", "/pricing", clicks=150, impressions=500, position=1.5))
    await db.commit()

    result = await get_search_opportunities(db, property_id=prop.id, as_of=today)

    striking_queries = {r["query"] for r in result["striking_distance_keywords"]}
    assert "buy widgets online" in striking_queries
    assert "widget pricing" not in striking_queries

    low_ctr_queries = {r["query"] for r in result["low_ctr_opportunities"]}
    assert "widget reviews" in low_ctr_queries
    assert "widget pricing" not in low_ctr_queries


@pytest.mark.asyncio
async def test_declining_and_rising_keywords(db):
    prop = await _make_property(db)
    today = date.today()

    # Previous period (29-56 days ago): "old favorite" did well.
    db.add(_metric(prop.id, today - timedelta(days=40), "old favorite", "/old", clicks=200, impressions=1000, position=3.0))
    # Current period (0-28 days ago): "old favorite" collapsed.
    db.add(_metric(prop.id, today - timedelta(days=5), "old favorite", "/old", clicks=20, impressions=900, position=5.0))

    # Previous period: "new star" was weak.
    db.add(_metric(prop.id, today - timedelta(days=40), "new star", "/new", clicks=15, impressions=200, position=9.0))
    # Current period: "new star" is thriving.
    db.add(_metric(prop.id, today - timedelta(days=5), "new star", "/new", clicks=180, impressions=900, position=3.0))
    await db.commit()

    result = await get_search_opportunities(db, property_id=prop.id, as_of=today)

    declining = {r["query"] for r in result["declining_keywords"]}
    rising = {r["query"] for r in result["rising_keywords"]}
    assert "old favorite" in declining
    assert "new star" in rising
    assert "old favorite" not in rising
    assert "new star" not in declining


@pytest.mark.asyncio
async def test_keyword_cannibalization(db):
    prop = await _make_property(db)
    today = date.today()

    # Same query ranking via two different pages -> cannibalization.
    db.add(_metric(prop.id, today - timedelta(days=5), "shared keyword", "/page-a", clicks=10, impressions=200, position=6.0))
    db.add(_metric(prop.id, today - timedelta(days=5), "shared keyword", "/page-b", clicks=8, impressions=150, position=9.0))
    # A query with only one ranking page -> not cannibalization.
    db.add(_metric(prop.id, today - timedelta(days=5), "unique keyword", "/page-c", clicks=50, impressions=300, position=2.0))
    await db.commit()

    result = await get_search_opportunities(db, property_id=prop.id, as_of=today)

    cannibalized_queries = {r["query"] for r in result["keyword_cannibalization"]}
    assert "shared keyword" in cannibalized_queries
    assert "unique keyword" not in cannibalized_queries

    entry = next(r for r in result["keyword_cannibalization"] if r["query"] == "shared keyword")
    assert len(entry["competing_pages"]) == 2


@pytest.mark.asyncio
async def test_high_impressions_no_clicks(db):
    prop = await _make_property(db)
    today = date.today()

    db.add(_metric(prop.id, today - timedelta(days=5), "ignored query", "/ignored", clicks=0, impressions=300, position=15.0))
    db.add(_metric(prop.id, today - timedelta(days=5), "clicked query", "/clicked", clicks=5, impressions=300, position=15.0))
    await db.commit()

    result = await get_search_opportunities(db, property_id=prop.id, as_of=today)
    zero_click_queries = {r["query"] for r in result["high_impressions_no_clicks"]}
    assert "ignored query" in zero_click_queries
    assert "clicked query" not in zero_click_queries
