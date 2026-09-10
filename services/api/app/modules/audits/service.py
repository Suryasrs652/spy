from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ConflictError, NotFoundError
from app.modules.audits.models import Audit, AuditJob, AuditStatus, TERMINAL_STATUSES
from app.modules.auth.models import User
from app.modules.entitlements.service import create_audit_with_entitlement
from app.modules.organizations.models import Organization
from app.modules.projects.service import get_project
from app.modules.recommendations.models import Recommendation
from app.modules.seo.models import AuditIssue, SEVERITY_ORDER, Severity


async def start_audit(
    db: AsyncSession,
    *,
    organization: Organization,
    user: User,
    project_id: uuid.UUID,
    requested_max_urls: int | None,
) -> Audit:
    project = await get_project(db, organization_id=organization.id, project_id=project_id)
    audit = await create_audit_with_entitlement(
        db,
        organization=organization,
        user=user,
        project=project,
        requested_max_urls=requested_max_urls,
    )
    return audit


async def get_audit(db: AsyncSession, *, organization_id: uuid.UUID, audit_id: uuid.UUID) -> Audit:
    result = await db.execute(
        select(Audit).where(Audit.id == audit_id, Audit.organization_id == organization_id)
    )
    audit = result.scalar_one_or_none()
    if audit is None:
        raise NotFoundError("Audit not found.")
    return audit


async def get_audit_progress(db: AsyncSession, *, organization_id: uuid.UUID, audit_id: uuid.UUID) -> AuditJob:
    audit = await get_audit(db, organization_id=organization_id, audit_id=audit_id)
    result = await db.execute(select(AuditJob).where(AuditJob.audit_id == audit.id))
    job = result.scalar_one_or_none()
    if job is None:
        raise NotFoundError("Audit job not found.")
    return job


async def list_audit_issues(
    db: AsyncSession, *, organization_id: uuid.UUID, audit_id: uuid.UUID
) -> list[AuditIssue]:
    audit = await get_audit(db, organization_id=organization_id, audit_id=audit_id)
    result = await db.execute(select(AuditIssue).where(AuditIssue.audit_id == audit.id))
    issues = list(result.scalars().all())
    issues.sort(key=lambda i: SEVERITY_ORDER.get(Severity(i.severity), 99))
    return issues


async def list_audit_pages(
    db: AsyncSession, *, organization_id: uuid.UUID, audit_id: uuid.UUID, limit: int = 200, offset: int = 0
):
    from app.modules.crawler.models import CrawlPage

    audit = await get_audit(db, organization_id=organization_id, audit_id=audit_id)
    result = await db.execute(
        select(CrawlPage)
        .where(CrawlPage.audit_id == audit.id)
        .order_by(CrawlPage.crawl_depth, CrawlPage.url)
        .limit(limit)
        .offset(offset)
    )
    return list(result.scalars().all())


async def list_recommendations(
    db: AsyncSession, *, organization_id: uuid.UUID, audit_id: uuid.UUID
) -> list[Recommendation]:
    audit = await get_audit(db, organization_id=organization_id, audit_id=audit_id)
    result = await db.execute(
        select(Recommendation)
        .where(Recommendation.audit_id == audit.id)
        .order_by(Recommendation.priority_score.desc())
    )
    return list(result.scalars().all())


async def cancel_audit(db: AsyncSession, *, organization_id: uuid.UUID, audit_id: uuid.UUID) -> Audit:
    from app.modules.audits.models import FailureCategory, FailureCode
    from app.modules.entitlements.service import release_entitlement_for_audit

    audit = await get_audit(db, organization_id=organization_id, audit_id=audit_id)
    if audit.status in [s.value for s in TERMINAL_STATUSES]:
        raise ConflictError("This audit has already finished and cannot be cancelled.")

    audit.status = AuditStatus.CANCELLED.value
    audit.failure_category = FailureCategory.USER_ERROR.value
    audit.failure_code = FailureCode.CANCELLED_BY_USER.value
    audit.failure_message = "Cancelled by user."

    # §4: cancelling before/during crawl must not consume the entitlement.
    # Committed together with the CANCELLED status above in one transaction
    # (release_entitlement_for_audit itself does not commit) so the two
    # never land as visibly-separate states.
    await release_entitlement_for_audit(db, audit)
    await db.commit()
    return audit
