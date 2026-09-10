from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Header
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import AuthContext, get_current_user, require_role
from app.core.idempotency import run_idempotent
from app.core.ratelimit import rate_limit_dependency
from app.db.session import get_db
from app.modules.audits import service
from app.modules.audits.schemas import (
    AuditCreateRequest,
    AuditIssueOut,
    AuditOut,
    AuditPageOut,
    AuditProgressOut,
    RecommendationOut,
)
from app.modules.auth.models import User
from app.modules.organizations.models import ROLE_CAN_RUN_AUDITS, ROLE_CAN_VIEW, Organization

router = APIRouter(prefix="/audits", tags=["audits"])


@router.post(
    "",
    response_model=AuditOut,
    status_code=201,
    dependencies=[Depends(rate_limit_dependency("audit_create", limit=20, window_seconds=60))],
)
async def create_audit(
    payload: AuditCreateRequest,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    ctx: AuthContext = Depends(require_role(*ROLE_CAN_RUN_AUDITS)),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> AuditOut:
    organization = (
        await db.execute(select(Organization).where(Organization.id == ctx.organization_id))
    ).scalar_one()

    async def _do() -> tuple[int, dict]:
        audit = await service.start_audit(
            db,
            organization=organization,
            user=user,
            project_id=payload.project_id,
            requested_max_urls=payload.max_urls,
        )
        # §157: enqueue the crawl only after the entitlement transaction has
        # committed (start_audit commits internally) — never inside it, so a
        # broker outage can't leave a reserved-but-unqueued audit stuck.
        from app.workers.tasks.crawl import run_audit_task

        run_audit_task.delay(str(audit.id))
        return 201, AuditOut.model_validate(audit).model_dump(mode="json")

    status_code, body = await run_idempotent(
        db,
        organization_id=ctx.organization_id,
        endpoint="POST /audits",
        idempotency_key=idempotency_key,
        fn=_do,
    )
    return AuditOut.model_validate(body)


@router.get("/{audit_id}", response_model=AuditOut)
async def get_audit(
    audit_id: uuid.UUID,
    ctx: AuthContext = Depends(require_role(*ROLE_CAN_VIEW)),
    db: AsyncSession = Depends(get_db),
) -> AuditOut:
    audit = await service.get_audit(db, organization_id=ctx.organization_id, audit_id=audit_id)
    return AuditOut.model_validate(audit)


@router.get("/{audit_id}/progress", response_model=AuditProgressOut)
async def get_audit_progress(
    audit_id: uuid.UUID,
    ctx: AuthContext = Depends(require_role(*ROLE_CAN_VIEW)),
    db: AsyncSession = Depends(get_db),
) -> AuditProgressOut:
    job = await service.get_audit_progress(db, organization_id=ctx.organization_id, audit_id=audit_id)
    return AuditProgressOut.model_validate(job)


@router.get("/{audit_id}/issues", response_model=list[AuditIssueOut])
async def get_audit_issues(
    audit_id: uuid.UUID,
    ctx: AuthContext = Depends(require_role(*ROLE_CAN_VIEW)),
    db: AsyncSession = Depends(get_db),
) -> list[AuditIssueOut]:
    issues = await service.list_audit_issues(db, organization_id=ctx.organization_id, audit_id=audit_id)
    return [AuditIssueOut.model_validate(i) for i in issues]


@router.get("/{audit_id}/pages", response_model=list[AuditPageOut])
async def get_audit_pages(
    audit_id: uuid.UUID,
    limit: int = 200,
    offset: int = 0,
    ctx: AuthContext = Depends(require_role(*ROLE_CAN_VIEW)),
    db: AsyncSession = Depends(get_db),
) -> list[AuditPageOut]:
    pages = await service.list_audit_pages(
        db, organization_id=ctx.organization_id, audit_id=audit_id, limit=limit, offset=offset
    )
    return [AuditPageOut.model_validate(p) for p in pages]


@router.get("/{audit_id}/recommendations", response_model=list[RecommendationOut])
async def get_audit_recommendations(
    audit_id: uuid.UUID,
    ctx: AuthContext = Depends(require_role(*ROLE_CAN_VIEW)),
    db: AsyncSession = Depends(get_db),
) -> list[RecommendationOut]:
    recs = await service.list_recommendations(db, organization_id=ctx.organization_id, audit_id=audit_id)
    return [RecommendationOut.model_validate(r) for r in recs]


@router.post("/{audit_id}/cancel", response_model=AuditOut)
async def cancel_audit(
    audit_id: uuid.UUID,
    ctx: AuthContext = Depends(require_role(*ROLE_CAN_RUN_AUDITS)),
    db: AsyncSession = Depends(get_db),
) -> AuditOut:
    audit = await service.cancel_audit(db, organization_id=ctx.organization_id, audit_id=audit_id)
    return AuditOut.model_validate(audit)
