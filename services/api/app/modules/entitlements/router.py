from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import AuthContext, get_auth_context, get_current_user
from app.db.session import get_db
from app.modules.auth.models import User
from app.modules.entitlements.schemas import EntitlementAuditOut
from app.modules.entitlements.service import get_entitlement_status

router = APIRouter(prefix="/entitlements", tags=["entitlements"])


@router.get("/audit", response_model=EntitlementAuditOut)
async def entitlement_audit_status(
    ctx: AuthContext = Depends(get_auth_context),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> EntitlementAuditOut:
    decision = await get_entitlement_status(db, organization_id=ctx.organization_id, user=user)
    return EntitlementAuditOut(
        can_run=decision.can_run, type=decision.type, remaining=decision.remaining, reason=decision.reason
    )
