"""§29 orchestrates one audit end-to-end:

QUEUED -> PREPARING -> CRAWLING -> ANALYZING -> SCORING -> GENERATING_REPORT
-> COMPLETED | FAILED

This is the only place all the pipeline pieces (crawler, rule engine,
scorer, recommendation engine, report generator, entitlement
consume/release) are wired together, matching §3's required shape:

    REAL DATA -> DETERMINISTIC ANALYSIS -> SCORING -> OPPORTUNITY -> REPORT
"""
from __future__ import annotations

import asyncio
import uuid

import structlog
from sqlalchemy import select

from app.core.errors import BlockedTargetError
from app.db.base import utcnow
from app.db.session import AsyncSessionLocal
from app.modules.admin.models import RuleConfig
from app.modules.audits.models import Audit, AuditJob, AuditStatus, FailureCategory, FailureCode
from app.modules.auth.models import User
from app.modules.crawler.engine import CrawlFailure, crawl_site
from app.modules.entitlements.service import consume_entitlement_for_audit, release_entitlement_for_audit
from app.modules.notifications.service import notify_audit_completed, notify_audit_failed
from app.modules.projects.models import Project
from app.modules.recommendations.engine import build_recommendations
from app.modules.recommendations.models import Recommendation
from app.modules.reports.service import generate_pdf_report
from app.modules.scoring.spy_score import compute_spy_score
from app.modules.seo.models import AuditIssue, AuditIssuePage
from app.modules.seo.rules import run_all_rules
from app.workers.celery_app import celery_app

logger = structlog.get_logger(__name__)


async def _load_active_rule_config(db) -> dict:
    """§131 — versioned thresholds live in the DB (seeded by migration
    0002), not hardcoded; DEFAULT_THRESHOLDS in rules/base.py is only the
    fallback for any key the active DB row doesn't (yet) override.
    """
    row = (
        await db.execute(
            select(RuleConfig).where(RuleConfig.key == "thresholds", RuleConfig.active.is_(True))
        )
    ).scalars().first()
    return dict(row.value) if row else {}


async def _set_status(db, audit: Audit, job: AuditJob, status: str, **job_fields) -> None:
    audit.status = status
    job.status = status
    job.heartbeat_at = utcnow()
    for k, v in job_fields.items():
        setattr(job, k, v)
    await db.commit()


async def _run_audit_async(audit_id: str) -> None:
    async with AsyncSessionLocal() as db:
        audit = (await db.execute(select(Audit).where(Audit.id == uuid.UUID(audit_id)))).scalar_one_or_none()
        if audit is None:
            logger.error("audit_not_found", audit_id=audit_id)
            return

        job = (await db.execute(select(AuditJob).where(AuditJob.audit_id == audit.id))).scalar_one_or_none()
        if job is None:
            logger.error("audit_job_not_found", audit_id=audit_id)
            return

        project = (await db.execute(select(Project).where(Project.id == audit.project_id))).scalar_one()

        try:
            audit.started_at = utcnow()
            job.started_at = utcnow()
            await _set_status(db, audit, job, AuditStatus.PREPARING.value)

            # project.canonical_origin was already normalized at project
            # creation time (app/modules/projects/service.py) — used as-is.
            origin = project.canonical_origin

            async def on_progress(processed: int, discovered: int) -> None:
                job.urls_processed = processed
                job.urls_discovered = discovered
                job.progress = int(100 * min(1.0, processed / max(discovered, 1)))
                job.heartbeat_at = utcnow()
                await db.commit()

            await _set_status(db, audit, job, AuditStatus.CRAWLING.value)
            result = await crawl_site(
                audit_id=audit.id, project_id=project.id, origin=origin,
                max_urls=audit.max_urls, on_progress=on_progress,
            )

            db.add_all(result.pages)
            db.add_all(result.links)
            await db.commit()

            await _set_status(
                db, audit, job, AuditStatus.ANALYZING.value,
                urls_processed=result.urls_processed, urls_discovered=result.urls_discovered, progress=100,
            )
            rule_config = await _load_active_rule_config(db)
            findings = run_all_rules(
                result.pages, result.links,
                rule_config=rule_config,
                site_facts={
                    "robots_txt_found": result.robots_txt_found,
                    "robots_disallow_all": result.robots_disallow_all,
                    "sitemap_found": result.sitemap_found,
                    "max_urls_reached": result.max_urls_reached,
                },
            )

            for finding in findings:
                issue = AuditIssue(
                    audit_id=audit.id, rule_id=finding.rule_id, category=finding.category,
                    severity=finding.severity.value, title=finding.title, description=finding.description,
                    recommendation=finding.recommendation, affected_count=finding.affected_count,
                    score_impact=finding.score_impact,
                )
                db.add(issue)
                await db.flush()
                for page_id, evidence in finding.affected:
                    db.add(AuditIssuePage(issue_id=issue.id, page_id=page_id, evidence=evidence))
            await db.commit()

            await _set_status(db, audit, job, AuditStatus.SCORING.value)
            score = compute_spy_score(
                pages=result.pages, findings=findings, urls_processed=result.urls_processed, links=result.links
            )
            audit.spy_score = score.spy_score
            audit.technical_score = score.technical_score
            audit.seo_score = score.seo_score
            audit.content_score = score.content_score
            audit.performance_score = score.performance_score
            audit.authority_score = score.authority_score
            audit.aeo_score = score.aeo_score
            audit.geo_score = score.geo_score
            audit.confidence = score.confidence
            audit.evidence = score.evidence
            await db.commit()

            recs = build_recommendations(findings, total_pages=len(result.pages))
            for r in recs:
                db.add(Recommendation(
                    id=r["id"], audit_id=audit.id, category=r["category"], title=r["title"],
                    description=r["description"], impact=r["impact"], confidence=r["confidence"],
                    effort=r["effort"], priority_score=r["priority_score"], status=r["status"],
                    group=r["group"], evidence=r["evidence"],
                ))
            await db.commit()

            await _set_status(db, audit, job, AuditStatus.GENERATING_REPORT.value)
            await generate_pdf_report(db, audit=audit)

            audit.completed_at = utcnow()
            job.completed_at = utcnow()
            audit.status = AuditStatus.COMPLETED.value
            job.status = AuditStatus.COMPLETED.value
            job.heartbeat_at = utcnow()
            # Committed together with the entitlement consumption below in
            # one transaction — see consume_entitlement_for_audit's
            # docstring for why splitting this into two commits is unsafe.
            await consume_entitlement_for_audit(db, audit)
            await db.commit()
            logger.info("audit_completed", audit_id=audit_id, spy_score=audit.spy_score)

            requester = (await db.execute(select(User).where(User.id == audit.requested_by))).scalar_one_or_none()
            if requester is not None:
                await notify_audit_completed(db, audit=audit, requester_email=requester.email)

        except CrawlFailure as exc:
            await _fail_audit(db, audit, job, category=exc.category, code=exc.code, message=exc.message)
        except BlockedTargetError as exc:
            await _fail_audit(db, audit, job, category=FailureCategory.USER_ERROR.value,
                               code=FailureCode.BLOCKED_TARGET.value, message=str(exc))
        except Exception as exc:  # noqa: BLE001 - last-resort classification
            logger.error("audit_worker_error", audit_id=audit_id, exc_info=True)
            await _fail_audit(db, audit, job, category=FailureCategory.SYSTEM_ERROR.value,
                               code=FailureCode.WORKER_ERROR.value, message=str(exc))


async def _fail_audit(db, audit: Audit, job: AuditJob, *, category: str, code: str, message: str) -> None:
    await db.rollback()
    audit.status = AuditStatus.FAILED.value
    audit.failure_category = category
    audit.failure_code = code
    audit.failure_message = message
    job.status = AuditStatus.FAILED.value
    job.error_code = code
    job.error_detail = message
    job.completed_at = utcnow()

    # §4/§30/§119: a qualifying failure releases the reserved entitlement so
    # the user is not charged their free audit (or a paid credit) for a
    # crawl that never produced a usable result. Committed in the same
    # transaction as the FAILED status above — see
    # release_entitlement_for_audit's docstring for why that matters.
    await release_entitlement_for_audit(db, audit)
    await db.commit()
    logger.warning("audit_failed", audit_id=str(audit.id), category=category, code=code)

    requester = (await db.execute(select(User).where(User.id == audit.requested_by))).scalar_one_or_none()
    if requester is not None:
        await notify_audit_failed(db, audit=audit, requester_email=requester.email)


@celery_app.task(name="app.workers.tasks.crawl.run_audit_task", bind=True, max_retries=0)
def run_audit_task(self, audit_id: str) -> None:
    asyncio.run(_run_audit_async(audit_id))
