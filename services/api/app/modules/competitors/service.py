"""§144/M5 — competitor benchmarking. See models.py for why this is
deliberately outside the paid-entitlement audit system.
"""
from __future__ import annotations

import uuid

import structlog
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ConflictError, NotFoundError, ValidationAppError
from app.db.base import utcnow
from app.modules.audits.models import Audit, AuditStatus
from app.modules.backlinks.service import record_discovered_backlinks
from app.modules.competitors.models import Competitor, CompetitorStatus
from app.modules.crawler.engine import CrawlFailure, crawl_site
from app.modules.crawler.normalize import canonical_origin
from app.modules.projects.service import get_project
from app.modules.scoring.pagerank import compute_internal_pagerank, normalize_to_100
from app.modules.scoring.spy_score import compute_spy_score
from app.modules.seo.rules import run_all_rules

logger = structlog.get_logger(__name__)

# A lighter crawl than a real audit's default (500) — this is a quick
# benchmark, not a full paid audit, and keeps a "compare 5 competitors"
# session from taking as long as auditing your own site five times over.
MAX_COMPETITOR_URLS = 100


async def add_competitor(
    db: AsyncSession, *, organization_id: uuid.UUID, project_id: uuid.UUID, name: str, url: str, user_id: uuid.UUID
) -> Competitor:
    project = await get_project(db, organization_id=organization_id, project_id=project_id)
    origin = canonical_origin(url)
    if origin == project.canonical_origin:
        raise ValidationAppError("A project can't be compared against itself.")

    competitor = Competitor(
        organization_id=organization_id, project_id=project_id, added_by=user_id,
        name=name.strip(), domain=origin.split("://", 1)[-1], canonical_origin=origin,
    )
    db.add(competitor)
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise ConflictError("This competitor has already been added to this project.") from exc
    await db.refresh(competitor)
    return competitor


async def list_competitors(db: AsyncSession, *, organization_id: uuid.UUID, project_id: uuid.UUID) -> list[Competitor]:
    result = await db.execute(
        select(Competitor)
        .where(Competitor.organization_id == organization_id, Competitor.project_id == project_id)
        .order_by(Competitor.created_at.desc())
    )
    return list(result.scalars().all())


async def get_competitor(
    db: AsyncSession, *, organization_id: uuid.UUID, project_id: uuid.UUID, competitor_id: uuid.UUID
) -> Competitor:
    result = await db.execute(
        select(Competitor).where(
            Competitor.id == competitor_id,
            Competitor.organization_id == organization_id,
            Competitor.project_id == project_id,
        )
    )
    competitor = result.scalar_one_or_none()
    if competitor is None:
        raise NotFoundError("Competitor not found.")
    return competitor


async def remove_competitor(
    db: AsyncSession, *, organization_id: uuid.UUID, project_id: uuid.UUID, competitor_id: uuid.UUID
) -> None:
    competitor = await get_competitor(db, organization_id=organization_id, project_id=project_id, competitor_id=competitor_id)
    await db.delete(competitor)
    await db.commit()


_COMPARISON_FIELDS = (
    "spy_score", "technical_score", "seo_score", "content_score", "performance_score", "aeo_score", "geo_score",
)


async def get_competitor_comparison(
    db: AsyncSession, *, organization_id: uuid.UUID, project_id: uuid.UUID, competitor_id: uuid.UUID
) -> dict:
    competitor = await get_competitor(db, organization_id=organization_id, project_id=project_id, competitor_id=competitor_id)

    latest_audit = (
        await db.execute(
            select(Audit)
            .where(
                Audit.organization_id == organization_id, Audit.project_id == project_id,
                Audit.status == AuditStatus.COMPLETED.value,
            )
            .order_by(Audit.created_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()

    comparisons = []
    for field in _COMPARISON_FIELDS:
        your_value = float(getattr(latest_audit, field)) if latest_audit and getattr(latest_audit, field) is not None else None
        competitor_value = float(getattr(competitor, field)) if getattr(competitor, field) is not None else None
        delta = (
            round(your_value - competitor_value, 2) if your_value is not None and competitor_value is not None else None
        )
        comparisons.append({
            "field": field, "your_score": your_value, "competitor_score": competitor_value, "delta": delta,
        })

    return {
        "competitor": competitor,
        "your_latest_audit_id": latest_audit.id if latest_audit else None,
        "comparisons": comparisons,
    }


async def run_competitor_benchmark(db: AsyncSession, *, competitor_id: uuid.UUID) -> None:
    """The actual crawl+score — called from the Celery task
    (app/workers/tasks/competitors.py), mirroring _run_audit_async's shape
    but never touching crawl_pages/page_links/audits: the crawled pages
    only ever exist in memory long enough to compute a score and feed the
    cross-site backlink index (app/modules/backlinks), matching this
    feature's "benchmark, not a persisted audit" scope.
    """
    competitor = (await db.execute(select(Competitor).where(Competitor.id == competitor_id))).scalar_one_or_none()
    if competitor is None:
        return

    competitor.status = CompetitorStatus.CRAWLING.value
    await db.commit()

    throwaway_audit_id = uuid.uuid4()
    try:
        result = await crawl_site(
            audit_id=throwaway_audit_id, project_id=competitor.project_id,
            origin=competitor.canonical_origin, max_urls=MAX_COMPETITOR_URLS,
        )

        pagerank_by_page_id = normalize_to_100(compute_internal_pagerank(result.pages, result.links))
        for page in result.pages:
            page.internal_pagerank = pagerank_by_page_id.get(page.id)

        findings = run_all_rules(result.pages, result.links)
        score = compute_spy_score(
            pages=result.pages, findings=findings, urls_processed=result.urls_processed, links=result.links,
        )

        try:
            await record_discovered_backlinks(db, audit_id=None, pages=result.pages, links=result.links)
        except Exception:  # noqa: BLE001
            logger.warning("competitor_backlink_recording_failed", competitor_id=str(competitor_id), exc_info=True)

        competitor.status = CompetitorStatus.COMPLETED.value
        competitor.last_crawled_at = utcnow()
        competitor.failure_message = None
        competitor.spy_score = score.spy_score
        competitor.technical_score = score.technical_score
        competitor.seo_score = score.seo_score
        competitor.content_score = score.content_score
        competitor.performance_score = score.performance_score
        competitor.aeo_score = score.aeo_score
        competitor.geo_score = score.geo_score
        competitor.evidence = score.evidence
        await db.commit()
        logger.info("competitor_benchmark_completed", competitor_id=str(competitor_id), spy_score=score.spy_score)
    except CrawlFailure as exc:
        await db.rollback()
        competitor.status = CompetitorStatus.FAILED.value
        competitor.failure_message = exc.message
        await db.commit()
    except Exception as exc:  # noqa: BLE001 - last-resort classification, mirrors _run_audit_async
        await db.rollback()
        logger.error("competitor_benchmark_error", competitor_id=str(competitor_id), exc_info=True)
        competitor.status = CompetitorStatus.FAILED.value
        competitor.failure_message = f"Unexpected error: {exc}"
        await db.commit()
