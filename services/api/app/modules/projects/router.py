from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import AuthContext, require_role
from app.db.session import get_db
from app.modules.organizations.models import ROLE_CAN_MANAGE_PROJECTS, ROLE_CAN_VIEW
from app.modules.projects import service
from app.modules.projects.schemas import ProjectCreateRequest, ProjectOut, ProjectUpdateRequest

router = APIRouter(prefix="/projects", tags=["projects"])


@router.get("", response_model=list[ProjectOut])
async def list_projects(
    ctx: AuthContext = Depends(require_role(*ROLE_CAN_VIEW)),
    db: AsyncSession = Depends(get_db),
) -> list[ProjectOut]:
    projects = await service.list_projects(db, organization_id=ctx.organization_id)
    return [ProjectOut.model_validate(p) for p in projects]


@router.post("", response_model=ProjectOut, status_code=201)
async def create_project(
    payload: ProjectCreateRequest,
    ctx: AuthContext = Depends(require_role(*ROLE_CAN_MANAGE_PROJECTS)),
    db: AsyncSession = Depends(get_db),
) -> ProjectOut:
    project = await service.create_project(
        db, organization_id=ctx.organization_id, name=payload.name, url=payload.url
    )
    return ProjectOut.model_validate(project)


@router.get("/{project_id}", response_model=ProjectOut)
async def get_project(
    project_id: uuid.UUID,
    ctx: AuthContext = Depends(require_role(*ROLE_CAN_VIEW)),
    db: AsyncSession = Depends(get_db),
) -> ProjectOut:
    project = await service.get_project(db, organization_id=ctx.organization_id, project_id=project_id)
    return ProjectOut.model_validate(project)


@router.patch("/{project_id}", response_model=ProjectOut)
async def update_project(
    project_id: uuid.UUID,
    payload: ProjectUpdateRequest,
    ctx: AuthContext = Depends(require_role(*ROLE_CAN_MANAGE_PROJECTS)),
    db: AsyncSession = Depends(get_db),
) -> ProjectOut:
    project = await service.update_project(
        db,
        organization_id=ctx.organization_id,
        project_id=project_id,
        name=payload.name,
        status=payload.status,
    )
    return ProjectOut.model_validate(project)


@router.delete("/{project_id}", status_code=204, response_model=None)
async def delete_project(
    project_id: uuid.UUID,
    ctx: AuthContext = Depends(require_role(*ROLE_CAN_MANAGE_PROJECTS)),
    db: AsyncSession = Depends(get_db),
) -> None:
    await service.delete_project(db, organization_id=ctx.organization_id, project_id=project_id)
