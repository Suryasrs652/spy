from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.deps import AuthContext, require_role
from app.core.ratelimit import rate_limit_dependency
from app.db.session import get_db
from app.modules.gsc import reporting, service
from app.modules.gsc.models import GscConnection
from app.modules.gsc.opportunities import get_search_opportunities
from app.modules.gsc.schemas import (
    GscConnectUrlOut,
    GscPropertyOut,
    GscSelectPropertyRequest,
    GscSyncResultOut,
)
from app.modules.gsc.sync_service import sync_all_selected_properties, sync_property
from app.modules.organizations.models import ROLE_CAN_MANAGE_PROJECTS, ROLE_CAN_VIEW

router = APIRouter(tags=["gsc"])


@router.get("/integrations/gsc/connect", response_model=GscConnectUrlOut)
async def gsc_connect(ctx: AuthContext = Depends(require_role(*ROLE_CAN_MANAGE_PROJECTS))) -> GscConnectUrlOut:
    url = service.build_authorization_url(organization_id=ctx.organization_id, user_id=ctx.user_id)
    return GscConnectUrlOut(authorization_url=url)


@router.get("/integrations/gsc/callback")
async def gsc_callback(code: str, state: str, db: AsyncSession = Depends(get_db)) -> RedirectResponse:
    """Hit directly by Google's redirect in the user's browser — no bearer
    token is available here, so the signed `state` param (minted by
    `gsc_connect` above) is what authenticates and scopes this callback.
    """
    settings = get_settings()
    organization_id, user_id = service.decode_state(state)
    try:
        await service.complete_connection(db, organization_id=organization_id, user_id=user_id, code=code)
        return RedirectResponse(f"{settings.web_base_url}/settings/integrations?gsc=connected")
    except Exception:  # noqa: BLE001 - land the user back on settings with an error flag, not a raw 500 page
        return RedirectResponse(f"{settings.web_base_url}/settings/integrations?gsc=error")


@router.get("/gsc/properties", response_model=list[GscPropertyOut])
async def gsc_properties(
    ctx: AuthContext = Depends(require_role(*ROLE_CAN_MANAGE_PROJECTS)),
    db: AsyncSession = Depends(get_db),
) -> list[GscPropertyOut]:
    props = await service.list_properties(db, organization_id=ctx.organization_id)
    return [GscPropertyOut.model_validate(p) for p in props]


@router.post("/gsc/properties/{property_id}/connect", response_model=GscPropertyOut)
async def gsc_connect_property(
    property_id: uuid.UUID,
    payload: GscSelectPropertyRequest,
    ctx: AuthContext = Depends(require_role(*ROLE_CAN_MANAGE_PROJECTS)),
    db: AsyncSession = Depends(get_db),
) -> GscPropertyOut:
    prop = await service.select_property(
        db, organization_id=ctx.organization_id, property_id=property_id, project_id=payload.project_id
    )
    return GscPropertyOut.model_validate(prop)


@router.post(
    "/gsc/sync",
    response_model=GscSyncResultOut,
    dependencies=[Depends(rate_limit_dependency("gsc_sync", limit=5, window_seconds=60))],
)
async def gsc_sync(
    ctx: AuthContext = Depends(require_role(*ROLE_CAN_MANAGE_PROJECTS)),
    db: AsyncSession = Depends(get_db),
) -> GscSyncResultOut:
    """Manual trigger for this organization's selected properties — the
    same sync also runs automatically once daily (§33, Celery Beat).
    """
    props = [p for p in await service.list_properties(db, organization_id=ctx.organization_id) if p.selected]
    synced, failed = 0, 0
    for prop in props:
        connection = await db.get(GscConnection, prop.connection_id)
        try:
            await sync_property(db, prop=prop, connection=connection)
            synced += 1
        except Exception:  # noqa: BLE001 - one broken property shouldn't fail the whole request
            failed += 1
    return GscSyncResultOut(synced=synced, failed=failed, total=len(props))


@router.get("/gsc/performance")
async def gsc_performance(
    property_id: uuid.UUID,
    days: int = 28,
    ctx: AuthContext = Depends(require_role(*ROLE_CAN_VIEW)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    await service.get_property_for_org(db, organization_id=ctx.organization_id, property_id=property_id)
    return await reporting.get_performance_summary(db, property_id=property_id, days=days)


@router.get("/gsc/queries")
async def gsc_queries(
    property_id: uuid.UUID,
    days: int = 28,
    ctx: AuthContext = Depends(require_role(*ROLE_CAN_VIEW)),
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    await service.get_property_for_org(db, organization_id=ctx.organization_id, property_id=property_id)
    return await reporting.get_top_queries(db, property_id=property_id, days=days)


@router.get("/gsc/pages")
async def gsc_pages(
    property_id: uuid.UUID,
    days: int = 28,
    ctx: AuthContext = Depends(require_role(*ROLE_CAN_VIEW)),
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    await service.get_property_for_org(db, organization_id=ctx.organization_id, property_id=property_id)
    return await reporting.get_top_pages(db, property_id=property_id, days=days)


@router.get("/gsc/opportunities")
async def gsc_opportunities(
    property_id: uuid.UUID,
    ctx: AuthContext = Depends(require_role(*ROLE_CAN_VIEW)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    await service.get_property_for_org(db, organization_id=ctx.organization_id, property_id=property_id)
    return await get_search_opportunities(db, property_id=property_id)
