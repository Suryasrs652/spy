from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import AuthContext, require_role
from app.db.session import get_db
from app.modules.backlinks import service
from app.modules.backlinks.schemas import BacklinkOut, BacklinkSummaryOut
from app.modules.organizations.models import ROLE_CAN_VIEW
from app.modules.projects.service import get_project

router = APIRouter(prefix="/projects", tags=["backlinks"])


@router.get("/{project_id}/backlinks/summary", response_model=BacklinkSummaryOut)
async def backlinks_summary(
    project_id: uuid.UUID,
    ctx: AuthContext = Depends(require_role(*ROLE_CAN_VIEW)),
    db: AsyncSession = Depends(get_db),
) -> BacklinkSummaryOut:
    project = await get_project(db, organization_id=ctx.organization_id, project_id=project_id)
    summary = await service.get_backlink_summary(db, domain=project.domain)
    return BacklinkSummaryOut(**summary)


@router.get("/{project_id}/backlinks", response_model=list[BacklinkOut])
async def list_backlinks(
    project_id: uuid.UUID,
    limit: int = 100,
    offset: int = 0,
    ctx: AuthContext = Depends(require_role(*ROLE_CAN_VIEW)),
    db: AsyncSession = Depends(get_db),
) -> list[BacklinkOut]:
    project = await get_project(db, organization_id=ctx.organization_id, project_id=project_id)
    backlinks = await service.get_backlinks_for_domain(db, domain=project.domain, limit=limit, offset=offset)
    return [BacklinkOut.model_validate(b) for b in backlinks]
