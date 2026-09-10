"""§133 audit comparison — a pure diff over Audit/AuditIssue rows already in
Postgres, so these build the two audits directly (same pattern as
test_scoring.py/test_rules.py's fixture-based CrawlPage construction)
rather than running two real crawls.
"""
from __future__ import annotations

import uuid

import pytest

from app.core.errors import ConflictError, NotFoundError, ValidationAppError
from app.modules.audits.models import Audit, AuditStatus
from app.modules.audits.service import compare_audits
from app.modules.projects.models import Project
from app.modules.seo.models import AuditIssue, Severity


async def _make_project(db, *, organization_id: uuid.UUID) -> Project:
    project = Project(
        organization_id=organization_id, name="Test Site",
        domain="example.com", canonical_origin="https://example.com",
    )
    db.add(project)
    await db.flush()
    return project


async def _make_audit(
    db, *, organization_id, project_id, user_id, spy_score: float, status=AuditStatus.COMPLETED.value
) -> Audit:
    audit = Audit(
        organization_id=organization_id, project_id=project_id, requested_by=user_id,
        status=status, spy_score=spy_score, technical_score=spy_score, seo_score=spy_score,
        content_score=spy_score, performance_score=spy_score, aeo_score=spy_score, geo_score=spy_score,
        confidence=90,
    )
    db.add(audit)
    await db.flush()
    return audit


def _issue(audit_id, rule_id, *, category="Metadata", severity=Severity.MEDIUM, affected_count=1) -> AuditIssue:
    return AuditIssue(
        audit_id=audit_id, rule_id=rule_id, category=category, severity=severity.value,
        title=f"Issue {rule_id}", description="desc", recommendation="fix it", affected_count=affected_count,
        score_impact=-1.0,
    )


@pytest.mark.asyncio
async def test_compare_orders_chronologically_regardless_of_argument_order(db, verified_user):
    user, org_id, _token = verified_user
    project = await _make_project(db, organization_id=org_id)

    older = await _make_audit(db, organization_id=org_id, project_id=project.id, user_id=user.id, spy_score=60)
    newer = await _make_audit(db, organization_id=org_id, project_id=project.id, user_id=user.id, spy_score=80)
    await db.commit()

    result_a = await compare_audits(db, organization_id=org_id, audit_id=newer.id, other_audit_id=older.id)
    result_b = await compare_audits(db, organization_id=org_id, audit_id=older.id, other_audit_id=newer.id)

    for result in (result_a, result_b):
        assert result["baseline_audit_id"] == older.id
        assert result["current_audit_id"] == newer.id
        assert result["score_deltas"]["spy_score"]["baseline"] == 60.0
        assert result["score_deltas"]["spy_score"]["current"] == 80.0
        assert result["score_deltas"]["spy_score"]["delta"] == 20.0


@pytest.mark.asyncio
async def test_compare_diffs_issues_into_new_resolved_persisting(db, verified_user):
    user, org_id, _token = verified_user
    project = await _make_project(db, organization_id=org_id)

    baseline = await _make_audit(db, organization_id=org_id, project_id=project.id, user_id=user.id, spy_score=50)
    current = await _make_audit(db, organization_id=org_id, project_id=project.id, user_id=user.id, spy_score=70)
    db.add(_issue(baseline.id, "SEO_META_001"))  # resolved by current
    db.add(_issue(baseline.id, "SEO_LINK_002"))  # persists
    db.add(_issue(current.id, "SEO_LINK_002"))   # persists
    db.add(_issue(current.id, "SEO_SCHEMA_003"))  # new in current
    await db.commit()

    result = await compare_audits(db, organization_id=org_id, audit_id=current.id, other_audit_id=baseline.id)

    assert {i["rule_id"] for i in result["new_issues"]} == {"SEO_SCHEMA_003"}
    assert {i["rule_id"] for i in result["resolved_issues"]} == {"SEO_META_001"}
    assert {i["rule_id"] for i in result["persisting_issues"]} == {"SEO_LINK_002"}


@pytest.mark.asyncio
async def test_compare_rejects_audits_from_different_projects(db, verified_user):
    user, org_id, _token = verified_user
    project_a = await _make_project(db, organization_id=org_id)
    project_b = Project(
        organization_id=org_id, name="Other Site", domain="other.example", canonical_origin="https://other.example"
    )
    db.add(project_b)
    await db.flush()

    audit_a = await _make_audit(db, organization_id=org_id, project_id=project_a.id, user_id=user.id, spy_score=50)
    audit_b = await _make_audit(db, organization_id=org_id, project_id=project_b.id, user_id=user.id, spy_score=60)
    await db.commit()

    with pytest.raises(ValidationAppError):
        await compare_audits(db, organization_id=org_id, audit_id=audit_a.id, other_audit_id=audit_b.id)


@pytest.mark.asyncio
async def test_compare_rejects_non_completed_audits(db, verified_user):
    user, org_id, _token = verified_user
    project = await _make_project(db, organization_id=org_id)

    completed = await _make_audit(db, organization_id=org_id, project_id=project.id, user_id=user.id, spy_score=50)
    running = await _make_audit(
        db, organization_id=org_id, project_id=project.id, user_id=user.id, spy_score=None,
        status=AuditStatus.CRAWLING.value,
    )
    await db.commit()

    with pytest.raises(ConflictError):
        await compare_audits(db, organization_id=org_id, audit_id=completed.id, other_audit_id=running.id)


@pytest.mark.asyncio
async def test_compare_rejects_identical_audit_ids(db, verified_user):
    user, org_id, _token = verified_user
    project = await _make_project(db, organization_id=org_id)
    audit = await _make_audit(db, organization_id=org_id, project_id=project.id, user_id=user.id, spy_score=50)
    await db.commit()

    with pytest.raises(ValidationAppError):
        await compare_audits(db, organization_id=org_id, audit_id=audit.id, other_audit_id=audit.id)


@pytest.mark.asyncio
async def test_compare_is_tenant_scoped(db, verified_user):
    """§122 — an audit id from another org must 404, not leak into a diff."""
    user, org_id, _token = verified_user
    project = await _make_project(db, organization_id=org_id)
    audit_a = await _make_audit(db, organization_id=org_id, project_id=project.id, user_id=user.id, spy_score=50)
    audit_b = await _make_audit(db, organization_id=org_id, project_id=project.id, user_id=user.id, spy_score=60)
    await db.commit()

    other_org_id = uuid.uuid4()
    with pytest.raises(NotFoundError):
        await compare_audits(db, organization_id=other_org_id, audit_id=audit_a.id, other_audit_id=audit_b.id)
