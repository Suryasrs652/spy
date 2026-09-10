"""Project creation validates and canonicalizes the target immediately —
an SSRF-unsafe target is rejected at project-creation time (§107), not
deferred until the crawl actually starts, so the user gets fast feedback and
no attacker-controlled row (with a plausible-looking domain that resolves to
an internal address) ever sits in the database waiting for a future crawl.
"""
from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ConflictError, NotFoundError
from app.core.net.safe_client import validate_host_resolves_safely, validate_scheme_and_port
from app.modules.crawler.normalize import canonical_origin
from app.modules.projects.models import Project


async def create_project(
    db: AsyncSession, *, organization_id: uuid.UUID, name: str, url: str
) -> Project:
    _scheme, hostname, _port = validate_scheme_and_port(url)
    validate_host_resolves_safely(hostname)  # raises BlockedTargetError if unsafe

    origin = canonical_origin(url)

    project = Project(
        organization_id=organization_id,
        name=name,
        domain=hostname,
        canonical_origin=origin,
    )
    db.add(project)
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise ConflictError("A project for this domain already exists.") from exc

    await db.refresh(project)
    return project


async def get_project(db: AsyncSession, *, organization_id: uuid.UUID, project_id: uuid.UUID) -> Project:
    result = await db.execute(
        select(Project).where(Project.id == project_id, Project.organization_id == organization_id)
    )
    project = result.scalar_one_or_none()
    if project is None:
        # A project in a different org must look identical to "does not
        # exist" (§122) — never leak existence via a 403.
        raise NotFoundError("Project not found.")
    return project


async def list_projects(db: AsyncSession, *, organization_id: uuid.UUID) -> list[Project]:
    result = await db.execute(
        select(Project).where(Project.organization_id == organization_id).order_by(Project.created_at.desc())
    )
    return list(result.scalars().all())


async def update_project(
    db: AsyncSession,
    *,
    organization_id: uuid.UUID,
    project_id: uuid.UUID,
    name: str | None,
    status: str | None,
) -> Project:
    project = await get_project(db, organization_id=organization_id, project_id=project_id)
    if name is not None:
        project.name = name
    if status is not None:
        project.status = status
    await db.commit()
    await db.refresh(project)
    return project


async def delete_project(db: AsyncSession, *, organization_id: uuid.UUID, project_id: uuid.UUID) -> None:
    project = await get_project(db, organization_id=organization_id, project_id=project_id)
    await db.delete(project)
    await db.commit()
