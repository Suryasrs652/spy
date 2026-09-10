from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ConflictError, NotFoundError
from app.modules.audits.models import Audit, AuditStatus
from app.modules.audits.service import (
    list_audit_issues,
    list_recommendations,
)
from app.modules.projects.service import get_project
from app.modules.reports.models import Report, ReportFormat, ReportStatus
from app.modules.reports.pdf import render_html_to_pdf
from app.modules.reports.render import render_audit_report_html
from app.modules.reports.storage import (
    ensure_bucket,
    object_key,
    presigned_download_url,
    upload_bytes,
)


async def generate_pdf_report(db: AsyncSession, *, audit: Audit) -> Report:
    # The pipeline (app/workers/tasks/crawl.py) calls this *during* the
    # GENERATING_REPORT phase — before the audit is marked COMPLETED, by
    # design (generating the report is the last step before completion).
    # What actually must be true is "scoring has happened", checked via
    # spy_score rather than the status enum, so both that in-pipeline call
    # and a later on-demand regeneration (status already COMPLETED) work.
    if audit.status not in (AuditStatus.GENERATING_REPORT.value, AuditStatus.COMPLETED.value) or audit.spy_score is None:
        raise ConflictError("A report can only be generated once an audit has been scored.")

    project = await get_project(db, organization_id=audit.organization_id, project_id=audit.project_id)
    issues = await list_audit_issues(db, organization_id=audit.organization_id, audit_id=audit.id)
    recommendations = await list_recommendations(db, organization_id=audit.organization_id, audit_id=audit.id)

    report = Report(
        audit_id=audit.id, organization_id=audit.organization_id,
        format=ReportFormat.PDF.value, status=ReportStatus.GENERATING.value,
    )
    db.add(report)
    await db.flush()

    try:
        html = render_audit_report_html(
            audit=audit, project=project, issues=issues, recommendations=recommendations
        )
        pdf_bytes = await render_html_to_pdf(html)

        ensure_bucket()
        key = object_key(organization_id=audit.organization_id, audit_id=audit.id, filename=f"{report.id}.pdf")
        upload_bytes(key=key, data=pdf_bytes, content_type="application/pdf")

        from app.db.base import utcnow

        report.storage_key = key
        report.status = ReportStatus.READY.value
        report.generated_at = utcnow()
    except Exception:  # noqa: BLE001
        report.status = ReportStatus.FAILED.value
        raise
    finally:
        await db.commit()

    return report


async def get_latest_report(db: AsyncSession, *, organization_id: uuid.UUID, audit_id: uuid.UUID) -> Report:
    result = await db.execute(
        select(Report)
        .where(Report.audit_id == audit_id, Report.organization_id == organization_id)
        .order_by(Report.created_at.desc())
    )
    report = result.scalars().first()
    if report is None:
        raise NotFoundError("No report found for this audit.")
    return report


async def get_download_url(db: AsyncSession, *, organization_id: uuid.UUID, report_id: uuid.UUID) -> str:
    result = await db.execute(
        select(Report).where(Report.id == report_id, Report.organization_id == organization_id)
    )
    report = result.scalar_one_or_none()
    if report is None or report.status != ReportStatus.READY.value or not report.storage_key:
        raise NotFoundError("Report not found or not ready.")

    return presigned_download_url(key=report.storage_key, filename=f"spy-audit-{report.audit_id}.pdf")
