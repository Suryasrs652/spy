from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user
from app.db.session import get_db
from app.modules.auth.models import User
from app.modules.organizations.schemas import OrganizationOut
from app.modules.organizations.service import list_user_organizations

router = APIRouter(prefix="/organizations", tags=["organizations"])


@router.get("", response_model=list[OrganizationOut])
async def list_my_organizations(
    user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> list[OrganizationOut]:
    orgs = await list_user_organizations(db, user.id)
    return [OrganizationOut.model_validate(o) for o in orgs]
