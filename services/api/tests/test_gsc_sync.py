"""§32-§33 GSC sync — Google's own API is mocked (no live credentials in
this environment), but everything downstream (DB writes, idempotent
re-sync, date-range selection) runs for real against Postgres.
"""
from __future__ import annotations

from datetime import date, timedelta

import pytest
from sqlalchemy import select

from app.modules.gsc.models import GscConnection, GscConnectionStatus, GscDailyMetric, GscProperty
from app.modules.gsc.sync_service import sync_property


async def _make_property_and_connection(db):
    from app.core.local_workspace import LOCAL_ORG_ID, get_local_user

    user = await get_local_user(db)
    org_id = LOCAL_ORG_ID

    connection = GscConnection(
        organization_id=org_id, user_id=user.id, google_account_id="test-account",
        encrypted_refresh_token="ciphertext-not-used-because-refresh-is-mocked",
        scopes=[], status=GscConnectionStatus.ACTIVE.value,
    )
    db.add(connection)
    await db.flush()

    prop = GscProperty(connection_id=connection.id, site_url="https://example.com/", permission_level="siteOwner", selected=True)
    db.add(prop)
    await db.commit()
    await db.refresh(prop)
    await db.refresh(connection)
    return prop, connection


def _fake_rows(day: date, n: int = 3) -> list[dict]:
    return [
        {
            "keys": [day.isoformat(), f"query-{i}", f"/page-{i}", "usa", "DESKTOP"],
            "clicks": 10 + i, "impressions": 100 + i * 10, "ctr": 0.1, "position": float(i + 1),
        }
        for i in range(n)
    ]


@pytest.mark.asyncio
async def test_sync_writes_rows_and_updates_last_sync(db, monkeypatch):
    prop, connection = await _make_property_and_connection(db)
    today = date.today()

    async def fake_refresh(_encrypted):
        return "fake-access-token"

    async def fake_query(*, access_token, site_url, start_date, end_date, dimensions):
        assert access_token == "fake-access-token"
        assert site_url == prop.site_url
        return _fake_rows(today - timedelta(days=3), n=3)

    monkeypatch.setattr("app.modules.gsc.sync_service.refresh_access_token", fake_refresh)
    monkeypatch.setattr("app.modules.gsc.sync_service.query_search_analytics", fake_query)

    assert connection.last_sync_at is None

    row_count = await sync_property(db, prop=prop, connection=connection)
    assert row_count == 3

    result = await db.execute(select(GscDailyMetric).where(GscDailyMetric.property_id == prop.id))
    rows = result.scalars().all()
    assert len(rows) == 3
    assert {r.query for r in rows} == {"query-0", "query-1", "query-2"}

    await db.refresh(connection)
    assert connection.last_sync_at is not None


@pytest.mark.asyncio
async def test_resync_replaces_rather_than_duplicates(db, monkeypatch):
    prop, connection = await _make_property_and_connection(db)
    today = date.today()
    target_day = today - timedelta(days=3)

    async def fake_refresh(_encrypted):
        return "fake-access-token"

    call_count = {"n": 0}

    async def fake_query(*, access_token, site_url, start_date, end_date, dimensions):
        call_count["n"] += 1
        # Second call returns DIFFERENT data for the same day — simulating
        # Google revising a not-yet-settled day (§33).
        clicks_offset = 0 if call_count["n"] == 1 else 100
        return [
            {
                "keys": [target_day.isoformat(), "steady-query", "/steady-page", "usa", "DESKTOP"],
                "clicks": 5 + clicks_offset, "impressions": 50, "ctr": 0.1, "position": 3.0,
            }
        ]

    monkeypatch.setattr("app.modules.gsc.sync_service.refresh_access_token", fake_refresh)
    monkeypatch.setattr("app.modules.gsc.sync_service.query_search_analytics", fake_query)

    await sync_property(db, prop=prop, connection=connection)
    await sync_property(db, prop=prop, connection=connection)

    result = await db.execute(
        select(GscDailyMetric).where(GscDailyMetric.property_id == prop.id, GscDailyMetric.query == "steady-query")
    )
    rows = result.scalars().all()
    assert len(rows) == 1, "re-syncing the same day must replace, not duplicate, the row"
    assert rows[0].clicks == 105, "the second (revised) sync's data should be what's stored"
