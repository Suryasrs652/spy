from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import AuthContext, get_current_user, require_role
from app.db.session import get_db
from app.modules.auth.models import User
from app.modules.keywords import service
from app.modules.keywords.schemas import (
    RankHistoryOut,
    RankOverviewRowOut,
    TrackedKeywordCreate,
    TrackedKeywordOut,
)
from app.modules.organizations.models import ROLE_CAN_MANAGE_PROJECTS, ROLE_CAN_VIEW
from app.modules.projects.service import get_project

router = APIRouter(prefix="/projects", tags=["keywords"])


@router.get("/{project_id}/keywords", response_model=list[RankOverviewRowOut])
async def list_keywords(
    project_id: uuid.UUID,
    days: int = 90,
    ctx: AuthContext = Depends(require_role(*ROLE_CAN_VIEW)),
    db: AsyncSession = Depends(get_db),
) -> list[RankOverviewRowOut]:
    await get_project(db, organization_id=ctx.organization_id, project_id=project_id)
    overview = await service.get_rank_overview(db, organization_id=ctx.organization_id, project_id=project_id, days=days)
    return [RankOverviewRowOut(**row) for row in overview]


@router.post("/{project_id}/keywords", response_model=TrackedKeywordOut, status_code=201)
async def add_keyword(
    project_id: uuid.UUID,
    payload: TrackedKeywordCreate,
    ctx: AuthContext = Depends(require_role(*ROLE_CAN_MANAGE_PROJECTS)),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> TrackedKeywordOut:
    await get_project(db, organization_id=ctx.organization_id, project_id=project_id)
    tracked = await service.add_tracked_keyword(
        db, organization_id=ctx.organization_id, project_id=project_id, keyword=payload.keyword, user_id=user.id
    )
    return TrackedKeywordOut.model_validate(tracked)


@router.delete("/{project_id}/keywords/{keyword_id}", status_code=204)
async def remove_keyword(
    project_id: uuid.UUID,
    keyword_id: uuid.UUID,
    ctx: AuthContext = Depends(require_role(*ROLE_CAN_MANAGE_PROJECTS)),
    db: AsyncSession = Depends(get_db),
) -> None:
    await get_project(db, organization_id=ctx.organization_id, project_id=project_id)
    await service.remove_tracked_keyword(db, organization_id=ctx.organization_id, project_id=project_id, keyword_id=keyword_id)


@router.get("/{project_id}/keywords/{keyword}/history", response_model=RankHistoryOut)
async def keyword_history(
    project_id: uuid.UUID,
    keyword: str,
    days: int = 90,
    ctx: AuthContext = Depends(require_role(*ROLE_CAN_VIEW)),
    db: AsyncSession = Depends(get_db),
) -> RankHistoryOut:
    await get_project(db, organization_id=ctx.organization_id, project_id=project_id)
    history = await service.get_keyword_rank_history(db, project_id=project_id, keyword=keyword, days=days)
    return RankHistoryOut(**history)
