"""§144/M5 competitor benchmarking — deliberately outside the paid-
entitlement audit system (see app/modules/competitors/models.py)."""
from __future__ import annotations

import uuid

import pytest

from app.core.errors import ConflictError, NotFoundError, ValidationAppError
from app.modules.audits.models import Audit, AuditStatus
from app.modules.competitors.models import CompetitorStatus
from app.modules.competitors.service import (
    add_competitor,
    get_competitor_comparison,
    get_content_gap_analysis,
    list_competitors,
    remove_competitor,
    run_competitor_benchmark,
)
from app.modules.projects.models import Project


async def _make_project(db, *, organization_id, domain="my-site.example"):
    project = Project(organization_id=organization_id, name="My Site", domain=domain, canonical_origin=f"https://{domain}")
    db.add(project)
    await db.commit()
    await db.refresh(project)
    return project


@pytest.mark.asyncio
async def test_add_list_and_remove_competitor(db, verified_user):
    user, org_id, _token = verified_user
    project = await _make_project(db, organization_id=org_id)

    competitor = await add_competitor(
        db, organization_id=org_id, project_id=project.id, name="Rival Co", url="https://rival.example/pricing", user_id=user.id,
    )
    assert competitor.domain == "rival.example"
    assert competitor.status == CompetitorStatus.PENDING.value

    competitors = await list_competitors(db, organization_id=org_id, project_id=project.id)
    assert len(competitors) == 1

    await remove_competitor(db, organization_id=org_id, project_id=project.id, competitor_id=competitor.id)
    assert await list_competitors(db, organization_id=org_id, project_id=project.id) == []


@pytest.mark.asyncio
async def test_cannot_add_own_project_as_competitor(db, verified_user):
    user, org_id, _token = verified_user
    project = await _make_project(db, organization_id=org_id, domain="self-compare.example")

    with pytest.raises(ValidationAppError):
        await add_competitor(
            db, organization_id=org_id, project_id=project.id, name="Me", url="https://self-compare.example/", user_id=user.id,
        )


@pytest.mark.asyncio
async def test_duplicate_competitor_rejected(db, verified_user):
    user, org_id, _token = verified_user
    project = await _make_project(db, organization_id=org_id, domain="dup-test.example")

    await add_competitor(db, organization_id=org_id, project_id=project.id, name="Rival", url="https://rival2.example/", user_id=user.id)
    with pytest.raises(ConflictError):
        await add_competitor(
            db, organization_id=org_id, project_id=project.id, name="Rival Again", url="https://rival2.example/other-page",
            user_id=user.id,
        )


@pytest.mark.asyncio
async def test_removing_unknown_competitor_404s(db, verified_user):
    user, org_id, _token = verified_user
    project = await _make_project(db, organization_id=org_id, domain="unknown-competitor.example")

    with pytest.raises(NotFoundError):
        await remove_competitor(db, organization_id=org_id, project_id=project.id, competitor_id=uuid.uuid4())


@pytest.mark.asyncio
async def test_comparison_without_own_audit_reports_no_baseline(db, verified_user):
    user, org_id, _token = verified_user
    project = await _make_project(db, organization_id=org_id, domain="no-baseline.example")
    competitor = await add_competitor(
        db, organization_id=org_id, project_id=project.id, name="Rival", url="https://rival3.example/", user_id=user.id,
    )

    comparison = await get_competitor_comparison(db, organization_id=org_id, project_id=project.id, competitor_id=competitor.id)
    assert comparison["your_latest_audit_id"] is None
    assert all(row["your_score"] is None for row in comparison["comparisons"])


@pytest.mark.asyncio
async def test_comparison_uses_latest_completed_audit(db, verified_user):
    user, org_id, _token = verified_user
    project = await _make_project(db, organization_id=org_id, domain="with-baseline.example")
    competitor = await add_competitor(
        db, organization_id=org_id, project_id=project.id, name="Rival", url="https://rival4.example/", user_id=user.id,
    )
    competitor.spy_score = 60.0
    competitor.status = CompetitorStatus.COMPLETED.value
    await db.commit()

    db.add(Audit(
        organization_id=org_id, project_id=project.id, requested_by=user.id,
        status=AuditStatus.COMPLETED.value, spy_score=85.0,
    ))
    await db.commit()

    comparison = await get_competitor_comparison(db, organization_id=org_id, project_id=project.id, competitor_id=competitor.id)
    assert comparison["your_latest_audit_id"] is not None
    spy_row = next(r for r in comparison["comparisons"] if r["field"] == "spy_score")
    assert spy_row["your_score"] == 85.0
    assert spy_row["competitor_score"] == 60.0
    assert spy_row["delta"] == 25.0


@pytest.mark.asyncio
async def test_run_competitor_benchmark_against_a_real_site(db, verified_user):
    """End-to-end: a real crawl of a real small site, real scoring, no
    entitlement touched, no crawl_pages/page_links/audits rows created."""
    from sqlalchemy import func, select

    from app.modules.crawler.models import CrawlPage

    user, org_id, _token = verified_user
    project = await _make_project(db, organization_id=org_id, domain="real-benchmark-owner.example")
    competitor = await add_competitor(
        db, organization_id=org_id, project_id=project.id, name="Example", url="https://example.com/", user_id=user.id,
    )
    competitor_id = competitor.id

    before_count = (await db.execute(select(func.count()).select_from(CrawlPage))).scalar_one()

    await run_competitor_benchmark(db, competitor_id=competitor_id)

    db.expire_all()
    refreshed = (await db.execute(select(type(competitor)).where(type(competitor).id == competitor_id))).scalar_one()
    assert refreshed.status == CompetitorStatus.COMPLETED.value
    assert refreshed.spy_score is not None
    assert refreshed.last_crawled_at is not None

    after_count = (await db.execute(select(func.count()).select_from(CrawlPage))).scalar_one()
    assert after_count == before_count, "competitor crawls must never persist crawl_pages rows"


@pytest.mark.asyncio
async def test_content_gap_without_benchmark_reports_no_data(db, verified_user):
    user, org_id, _token = verified_user
    project = await _make_project(db, organization_id=org_id, domain="gap-no-benchmark.example")
    competitor = await add_competitor(
        db, organization_id=org_id, project_id=project.id, name="Rival", url="https://rival5.example/", user_id=user.id,
    )

    result = await get_content_gap_analysis(db, organization_id=org_id, project_id=project.id, competitor_id=competitor.id)
    assert result["has_data"] is False
    assert "benchmark" in result["reason"]


@pytest.mark.asyncio
async def test_content_gap_without_own_audit_reports_no_data(db, verified_user):
    user, org_id, _token = verified_user
    project = await _make_project(db, organization_id=org_id, domain="gap-no-audit.example")
    competitor = await add_competitor(
        db, organization_id=org_id, project_id=project.id, name="Rival", url="https://rival6.example/", user_id=user.id,
    )
    competitor.status = CompetitorStatus.COMPLETED.value
    competitor.evidence = {"top_terms": ["widgets", "pricing"]}
    await db.commit()

    result = await get_content_gap_analysis(db, organization_id=org_id, project_id=project.id, competitor_id=competitor.id)
    assert result["has_data"] is False
    assert "audit" in result["reason"]


@pytest.mark.asyncio
async def test_content_gap_finds_terms_competitor_covers_that_you_dont(db, verified_user):
    from app.modules.crawler.models import CrawlPage

    user, org_id, _token = verified_user
    project = await _make_project(db, organization_id=org_id, domain="gap-full.example")
    competitor = await add_competitor(
        db, organization_id=org_id, project_id=project.id, name="Rival", url="https://rival7.example/", user_id=user.id,
    )
    competitor.status = CompetitorStatus.COMPLETED.value
    competitor.evidence = {"top_terms": ["widgets", "shipping", "returns"]}
    await db.commit()

    audit = Audit(
        organization_id=org_id, project_id=project.id, requested_by=user.id,
        status=AuditStatus.COMPLETED.value, spy_score=70.0,
    )
    db.add(audit)
    await db.flush()
    db.add(CrawlPage(
        audit_id=audit.id, project_id=project.id, url="https://gap-full.example/",
        normalized_url="https://gap-full.example/", indexable=True,
        title="Best Widgets Online", h1="Widgets",
    ))
    await db.commit()

    result = await get_content_gap_analysis(db, organization_id=org_id, project_id=project.id, competitor_id=competitor.id)
    assert result["has_data"] is True
    assert "widgets" not in result["gap_terms"]
    assert "shipping" in result["gap_terms"]
    assert "returns" in result["gap_terms"]
