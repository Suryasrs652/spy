from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.deps import AuthContext, require_role
from app.db.session import get_db
from app.modules.gsc import service
from app.modules.gsc.schemas import GscConnectUrlOut, GscPropertyOut
from app.modules.organizations.models import ROLE_CAN_MANAGE_PROJECTS

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
