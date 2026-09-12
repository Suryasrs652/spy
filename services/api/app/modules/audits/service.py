from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ConflictError, NotFoundError, ValidationAppError
from app.db.base import utcnow
from app.modules.audits.models import (
    CURRENT_SCORE_VERSION,
    TERMINAL_STATUSES,
    Audit,
    AuditJob,
    AuditStatus,
)
from app.modules.auth.models import User
from app.modules.organizations.models import Organization
from app.modules.projects.service import get_project
from app.modules.recommendations.models import Recommendation
from app.modules.seo.models import SEVERITY_ORDER, AuditIssue, Severity

# Self-hosted and free: audits aren't metered, so the only cap left is the
# crawler's own ceiling on how much work one audit may do. It's still
# server-side — `requested_max_urls` is a client hint, never authority.
MAX_URLS = 2000


async def start_audit(
    db: AsyncSession,
    *,
    organization: Organization,
    user: User,
    project_id: uuid.UUID,
    requested_max_urls: int | None,
) -> Audit:
    project = await get_project(db, organization_id=organization.id, project_id=project_id)

    audit = Audit(
        organization_id=organization.id,
        project_id=project.id,
        requested_by=user.id,
        status=AuditStatus.QUEUED.value,
        max_urls=min(requested_max_urls, MAX_URLS) if requested_max_urls else MAX_URLS,
        score_version=CURRENT_SCORE_VERSION,
    )
    db.add(audit)
    await db.flush()

    db.add(AuditJob(audit_id=audit.id, status=AuditStatus.QUEUED.value))
    await db.commit()
    await db.refresh(audit)
    return audit


async def get_audit(db: AsyncSession, *, organization_id: uuid.UUID, audit_id: uuid.UUID) -> Audit:
    result = await db.execute(
        select(Audit).where(Audit.id == audit_id, Audit.organization_id == organization_id)
    )
    audit = result.scalar_one_or_none()
    if audit is None:
        raise NotFoundError("Audit not found.")
    return audit


async def list_audits_for_project(
    db: AsyncSession, *, organization_id: uuid.UUID, project_id: uuid.UUID
) -> list[Audit]:
    result = await db.execute(
        select(Audit)
        .where(Audit.organization_id == organization_id, Audit.project_id == project_id)
        .order_by(Audit.created_at.desc())
    )
    return list(result.scalars().all())


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


async def record_issue_validation(
    db: AsyncSession,
    *,
    organization_id: uuid.UUID,
    audit_id: uuid.UUID,
    issue_id: uuid.UUID,
    validated: bool,
    note: str | None = None,
) -> AuditIssue:
    """Record whether a finding held up when someone checked it against the
    live site.

    The rule engine can only report what the crawl saw. Anything it flags
    can still be wrong — markup injected after load, a host that answers
    bots differently, a threshold that doesn't fit this site. This is where
    that verdict lands, so a finding already shown to be false stops being
    re-litigated by every reader of the report.

    The verdict never edits the finding itself: `severity`, `confidence` and
    the evidence rows stay exactly as the rules produced them, which is what
    keeps an audit re-derivable from its own crawl (§21).
    """
    audit = await get_audit(db, organization_id=organization_id, audit_id=audit_id)
    issue = (
        await db.execute(
            select(AuditIssue).where(AuditIssue.id == issue_id, AuditIssue.audit_id == audit.id)
        )
    ).scalar_one_or_none()
    if issue is None:
        raise NotFoundError("Audit issue not found.")

    issue.validated = validated
    issue.validated_at = utcnow()
    issue.validation_note = note
    await db.commit()
    await db.refresh(issue)
    return issue


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


_COMPARABLE_SCORE_FIELDS = (
    "spy_score", "technical_score", "seo_score", "content_score",
    "performance_score", "authority_score", "aeo_score", "geo_score", "confidence",
)


def _issue_summary(issue: AuditIssue) -> dict:
    return {
        "rule_id": issue.rule_id, "category": issue.category, "severity": issue.severity,
        "title": issue.title, "affected_count": issue.affected_count,
    }


async def compare_audits(
    db: AsyncSession, *, organization_id: uuid.UUID, audit_id: uuid.UUID, other_audit_id: uuid.UUID
) -> dict:
    """§133 — diffs scores and issues between two completed audits of the
    same project. Both ids are resolved through `get_audit` (org-scoped) so
    a cross-tenant id 404s exactly like every other audit lookup (§122).
    """
    from app.modules.crawler.models import CrawlPage

    if audit_id == other_audit_id:
        raise ValidationAppError("Cannot compare an audit against itself.")

    audit_a = await get_audit(db, organization_id=organization_id, audit_id=audit_id)
    audit_b = await get_audit(db, organization_id=organization_id, audit_id=other_audit_id)

    if audit_a.project_id != audit_b.project_id:
        raise ValidationAppError("Audits being compared must belong to the same project.")
    for a in (audit_a, audit_b):
        if a.status != AuditStatus.COMPLETED.value:
            raise ConflictError("Both audits must be COMPLETED to compare.")

    baseline, current = sorted([audit_a, audit_b], key=lambda a: a.created_at)

    score_deltas = {}
    for field in _COMPARABLE_SCORE_FIELDS:
        b_val, c_val = getattr(baseline, field), getattr(current, field)
        score_deltas[field] = {
            "baseline": float(b_val) if b_val is not None else None,
            "current": float(c_val) if c_val is not None else None,
            "delta": round(float(c_val) - float(b_val), 2) if b_val is not None and c_val is not None else None,
        }

    baseline_issues = await list_audit_issues(db, organization_id=organization_id, audit_id=baseline.id)
    current_issues = await list_audit_issues(db, organization_id=organization_id, audit_id=current.id)
    baseline_by_rule = {i.rule_id: i for i in baseline_issues}
    current_by_rule = {i.rule_id: i for i in current_issues}

    new_issues = [_issue_summary(i) for rid, i in current_by_rule.items() if rid not in baseline_by_rule]
    resolved_issues = [_issue_summary(i) for rid, i in baseline_by_rule.items() if rid not in current_by_rule]
    persisting_issues = [
        _issue_summary(current_by_rule[rid]) for rid in current_by_rule if rid in baseline_by_rule
    ]

    baseline_page_count = (
        await db.execute(select(func.count()).select_from(CrawlPage).where(CrawlPage.audit_id == baseline.id))
    ).scalar_one()
    current_page_count = (
        await db.execute(select(func.count()).select_from(CrawlPage).where(CrawlPage.audit_id == current.id))
    ).scalar_one()

    return {
        "baseline_audit_id": baseline.id, "current_audit_id": current.id,
        "baseline_created_at": baseline.created_at, "current_created_at": current.created_at,
        "score_deltas": score_deltas,
        "new_issues": new_issues, "resolved_issues": resolved_issues, "persisting_issues": persisting_issues,
        "page_count_baseline": baseline_page_count, "page_count_current": current_page_count,
    }


async def cancel_audit(db: AsyncSession, *, organization_id: uuid.UUID, audit_id: uuid.UUID) -> Audit:
    from app.modules.audits.models import FailureCategory, FailureCode

    audit = await get_audit(db, organization_id=organization_id, audit_id=audit_id)
    if audit.status in [s.value for s in TERMINAL_STATUSES]:
        raise ConflictError("This audit has already finished and cannot be cancelled.")

    audit.status = AuditStatus.CANCELLED.value
    audit.failure_category = FailureCategory.USER_ERROR.value
    audit.failure_code = FailureCode.CANCELLED_BY_USER.value
    audit.failure_message = "Cancelled by user."

    await db.commit()
    return audit
