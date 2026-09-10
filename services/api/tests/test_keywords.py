"""§144/M5 rank tracking — built on real, already-synced GSC position data.
See app/modules/keywords/models.py for why this isn't a live SERP checker.
"""
from __future__ import annotations

from datetime import date, timedelta

import pytest

from app.core.errors import ConflictError, NotFoundError
from app.modules.gsc.models import GscConnection, GscConnectionStatus, GscDailyMetric, GscProperty
from app.modules.keywords.service import (
    add_tracked_keyword,
    get_keyword_rank_history,
    get_rank_overview,
    list_tracked_keywords,
    remove_tracked_keyword,
)
from app.modules.projects.models import Project
from tests.conftest import unique_email


async def _make_project(db, *, organization_id, name="Rank Test Site", domain="rank-test.example"):
    project = Project(organization_id=organization_id, name=name, domain=domain, canonical_origin=f"https://{domain}")
    db.add(project)
    await db.flush()
    return project


async def _connect_gsc_property(db, *, organization_id, user_id, project_id, site_url):
    connection = GscConnection(
        organization_id=organization_id, user_id=user_id, google_account_id="test-account",
        encrypted_refresh_token="unused-in-this-test", scopes=[], status=GscConnectionStatus.ACTIVE.value,
    )
    db.add(connection)
    await db.flush()
    prop = GscProperty(
        connection_id=connection.id, project_id=project_id, site_url=site_url,
        permission_level="siteOwner", selected=True,
    )
    db.add(prop)
    await db.commit()
    await db.refresh(prop)
    return prop


@pytest.mark.asyncio
async def test_add_list_and_remove_tracked_keyword(db, verified_user):
    user, org_id, _token = verified_user
    project = await _make_project(db, organization_id=org_id)
    await db.commit()

    tracked = await add_tracked_keyword(db, organization_id=org_id, project_id=project.id, keyword="  Best Widgets  ", user_id=user.id)
    assert tracked.keyword == "best widgets"

    keywords = await list_tracked_keywords(db, organization_id=org_id, project_id=project.id)
    assert [k.keyword for k in keywords] == ["best widgets"]

    await remove_tracked_keyword(db, organization_id=org_id, project_id=project.id, keyword_id=tracked.id)
    assert await list_tracked_keywords(db, organization_id=org_id, project_id=project.id) == []


@pytest.mark.asyncio
async def test_duplicate_keyword_rejected(db, verified_user):
    user, org_id, _token = verified_user
    project = await _make_project(db, organization_id=org_id)
    await db.commit()

    await add_tracked_keyword(db, organization_id=org_id, project_id=project.id, keyword="widgets", user_id=user.id)
    with pytest.raises(ConflictError):
        await add_tracked_keyword(db, organization_id=org_id, project_id=project.id, keyword="Widgets", user_id=user.id)


@pytest.mark.asyncio
async def test_removing_unknown_keyword_404s(db, verified_user):
    import uuid

    user, org_id, _token = verified_user
    project = await _make_project(db, organization_id=org_id)
    await db.commit()

    with pytest.raises(NotFoundError):
        await remove_tracked_keyword(db, organization_id=org_id, project_id=project.id, keyword_id=uuid.uuid4())


@pytest.mark.asyncio
async def test_history_reports_no_data_without_gsc_connection(db, verified_user):
    user, org_id, _token = verified_user
    project = await _make_project(db, organization_id=org_id, domain="no-gsc.example")
    await db.commit()

    history = await get_keyword_rank_history(db, project_id=project.id, keyword="anything")
    assert history["has_data"] is False
    assert "Search Console" in history["reason"]
    assert history["history"] == []


@pytest.mark.asyncio
async def test_history_reports_no_data_when_keyword_has_no_impressions(db, verified_user):
    user, org_id, _token = verified_user
    project = await _make_project(db, organization_id=org_id, domain="synced-no-kw.example")
    await _connect_gsc_property(db, organization_id=org_id, user_id=user.id, project_id=project.id, site_url="https://synced-no-kw.example/")

    history = await get_keyword_rank_history(db, project_id=project.id, keyword="untracked term")
    assert history["has_data"] is False
    assert "impressions" in history["reason"]


@pytest.mark.asyncio
async def test_history_returns_real_position_series(db, verified_user):
    user, org_id, _token = verified_user
    project = await _make_project(db, organization_id=org_id, domain="real-history.example")
    prop = await _connect_gsc_property(db, organization_id=org_id, user_id=user.id, project_id=project.id, site_url="https://real-history.example/")

    today = date.today()
    db.add_all([
        GscDailyMetric(
            property_id=prop.id, date=today - timedelta(days=2), query="Widget Reviews", page="/reviews",
            clicks=10, impressions=200, ctr=0.05, position=8.5,
        ),
        GscDailyMetric(
            property_id=prop.id, date=today - timedelta(days=1), query="widget reviews", page="/reviews",
            clicks=15, impressions=180, ctr=0.08, position=6.2,
        ),
    ])
    await db.commit()

    history = await get_keyword_rank_history(db, project_id=project.id, keyword="Widget Reviews")
    assert history["has_data"] is True
    assert len(history["history"]) == 2
    assert history["current_position"] == 6.2
    assert history["best_position"] == 6.2


@pytest.mark.asyncio
async def test_rank_overview_summarizes_every_tracked_keyword(db, verified_user):
    user, org_id, _token = verified_user
    project = await _make_project(db, organization_id=org_id, domain="overview.example")
    prop = await _connect_gsc_property(db, organization_id=org_id, user_id=user.id, project_id=project.id, site_url="https://overview.example/")

    await add_tracked_keyword(db, organization_id=org_id, project_id=project.id, keyword="has data", user_id=user.id)
    await add_tracked_keyword(db, organization_id=org_id, project_id=project.id, keyword="no data", user_id=user.id)

    db.add(GscDailyMetric(
        property_id=prop.id, date=date.today(), query="has data", page="/", clicks=1, impressions=50, ctr=0.02, position=4.0,
    ))
    await db.commit()

    overview = await get_rank_overview(db, organization_id=org_id, project_id=project.id)
    by_keyword = {row["keyword"]: row for row in overview}
    assert by_keyword["has data"]["has_data"] is True
    assert by_keyword["has data"]["current_position"] == 4.0
    assert by_keyword["no data"]["has_data"] is False
    assert by_keyword["no data"]["current_position"] is None
