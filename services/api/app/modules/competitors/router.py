from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import AuthContext, get_current_user, require_role
from app.core.ratelimit import rate_limit_dependency
from app.db.session import get_db
from app.modules.auth.models import User
from app.modules.competitors import service
from app.modules.competitors.schemas import (
    CompetitorComparisonOut,
    CompetitorCreate,
    CompetitorMatrixOut,
    CompetitorOut,
    ContentGapOut,
)
from app.modules.organizations.models import ROLE_CAN_MANAGE_PROJECTS, ROLE_CAN_VIEW

router = APIRouter(prefix="/projects", tags=["competitors"])


@router.get("/{project_id}/competitors", response_model=list[CompetitorOut])
async def list_competitors(
    project_id: uuid.UUID,
    ctx: AuthContext = Depends(require_role(*ROLE_CAN_VIEW)),
    db: AsyncSession = Depends(get_db),
) -> list[CompetitorOut]:
    competitors = await service.list_competitors(db, organization_id=ctx.organization_id, project_id=project_id)
    return [CompetitorOut.model_validate(c) for c in competitors]


@router.post("/{project_id}/competitors", response_model=CompetitorOut, status_code=201)
async def add_competitor(
    project_id: uuid.UUID,
    payload: CompetitorCreate,
    ctx: AuthContext = Depends(require_role(*ROLE_CAN_MANAGE_PROJECTS)),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> CompetitorOut:
    competitor = await service.add_competitor(
        db, organization_id=ctx.organization_id, project_id=project_id,
        name=payload.name, url=payload.url, user_id=user.id,
    )
    return CompetitorOut.model_validate(competitor)


@router.delete("/{project_id}/competitors/{competitor_id}", status_code=204)
async def remove_competitor(
    project_id: uuid.UUID,
    competitor_id: uuid.UUID,
    ctx: AuthContext = Depends(require_role(*ROLE_CAN_MANAGE_PROJECTS)),
    db: AsyncSession = Depends(get_db),
) -> None:
    await service.remove_competitor(db, organization_id=ctx.organization_id, project_id=project_id, competitor_id=competitor_id)


@router.post(
    "/{project_id}/competitors/{competitor_id}/refresh",
    status_code=202,
    dependencies=[Depends(rate_limit_dependency("competitor_refresh", limit=10, window_seconds=60))],
)
async def refresh_competitor(
    project_id: uuid.UUID,
    competitor_id: uuid.UUID,
    ctx: AuthContext = Depends(require_role(*ROLE_CAN_MANAGE_PROJECTS)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    # 404s if the competitor doesn't belong to this org/project before
    # enqueueing anything.
    await service.get_competitor(db, organization_id=ctx.organization_id, project_id=project_id, competitor_id=competitor_id)

    from app.workers.tasks.competitors import refresh_competitor_task

    refresh_competitor_task.delay(str(competitor_id))
    return {"queued": True}


@router.get("/{project_id}/competitors/matrix", response_model=CompetitorMatrixOut)
async def competitor_matrix(
    project_id: uuid.UUID,
    ctx: AuthContext = Depends(require_role(*ROLE_CAN_VIEW)),
    db: AsyncSession = Depends(get_db),
) -> CompetitorMatrixOut:
    """Your latest audit against every benchmarked competitor at once, plus
    the specific signals where they are ahead.
    """
    matrix = await service.get_competitor_matrix(
        db, organization_id=ctx.organization_id, project_id=project_id
    )
    return CompetitorMatrixOut.model_validate(matrix)


@router.get("/{project_id}/competitors/{competitor_id}/compare", response_model=CompetitorComparisonOut)
async def compare_competitor(
    project_id: uuid.UUID,
    competitor_id: uuid.UUID,
    ctx: AuthContext = Depends(require_role(*ROLE_CAN_VIEW)),
    db: AsyncSession = Depends(get_db),
) -> CompetitorComparisonOut:
    comparison = await service.get_competitor_comparison(
        db, organization_id=ctx.organization_id, project_id=project_id, competitor_id=competitor_id
    )
    return CompetitorComparisonOut(
        competitor=CompetitorOut.model_validate(comparison["competitor"]),
        your_latest_audit_id=comparison["your_latest_audit_id"],
        comparisons=comparison["comparisons"],
    )


@router.get("/{project_id}/competitors/{competitor_id}/content-gap", response_model=ContentGapOut)
async def content_gap(
    project_id: uuid.UUID,
    competitor_id: uuid.UUID,
    ctx: AuthContext = Depends(require_role(*ROLE_CAN_VIEW)),
    db: AsyncSession = Depends(get_db),
) -> ContentGapOut:
    result = await service.get_content_gap_analysis(
        db, organization_id=ctx.organization_id, project_id=project_id, competitor_id=competitor_id
    )
    return ContentGapOut(**result)
