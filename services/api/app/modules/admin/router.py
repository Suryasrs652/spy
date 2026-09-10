"""§96 admin endpoints — SUPER_ADMIN only.

M1 ships a functional slice (users/orgs/audits/feature-flags listing and
toggling) rather than a stub; revenue/queue/error dashboards (§129) are M3.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Header
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.errors import ForbiddenError, NotFoundError
from app.db.session import get_db
from app.modules.admin.models import FeatureFlag
from app.modules.audits.models import Audit
from app.modules.auth.models import User
from app.modules.organizations.models import Organization

router = APIRouter(prefix="/admin", tags=["admin"])


async def require_super_admin(x_internal_token: str | None = Header(default=None, alias="X-Internal-Token")) -> None:
    """M1's admin authorization is the same shared internal token used for
    service-to-service calls — a real SUPER_ADMIN role/session check
    belongs in M3's admin dashboard build-out (§128/§129); until then this
    keeps the surface unreachable from a normal user session rather than
    leaving it open.
    """
    settings = get_settings()
    if not x_internal_token or x_internal_token != settings.internal_service_token:
        raise ForbiddenError("Admin access required.")


@router.get("/users", dependencies=[Depends(require_super_admin)])
async def list_users(db: AsyncSession = Depends(get_db), limit: int = 50, offset: int = 0) -> list[dict]:
    result = await db.execute(select(User).order_by(User.created_at.desc()).limit(limit).offset(offset))
    return [
        {"id": str(u.id), "email": u.email, "status": u.status, "email_verified": u.is_email_verified,
         "created_at": u.created_at.isoformat()}
        for u in result.scalars().all()
    ]


@router.get("/organizations", dependencies=[Depends(require_super_admin)])
async def list_organizations(db: AsyncSession = Depends(get_db), limit: int = 50, offset: int = 0) -> list[dict]:
    result = await db.execute(select(Organization).order_by(Organization.created_at.desc()).limit(limit).offset(offset))
    return [{"id": str(o.id), "name": o.name, "slug": o.slug} for o in result.scalars().all()]


@router.get("/audits", dependencies=[Depends(require_super_admin)])
async def list_all_audits(db: AsyncSession = Depends(get_db), limit: int = 50, offset: int = 0) -> list[dict]:
    result = await db.execute(select(Audit).order_by(Audit.created_at.desc()).limit(limit).offset(offset))
    return [
        {"id": str(a.id), "status": a.status, "spy_score": float(a.spy_score) if a.spy_score is not None else None,
         "failure_code": a.failure_code, "created_at": a.created_at.isoformat()}
        for a in result.scalars().all()
    ]


@router.get("/overview", dependencies=[Depends(require_super_admin)])
async def overview(db: AsyncSession = Depends(get_db)) -> dict:
    total_users = (await db.execute(select(func.count()).select_from(User))).scalar_one()
    verified_users = (
        await db.execute(select(func.count()).select_from(User).where(User.email_verified_at.isnot(None)))
    ).scalar_one()
    total_audits = (await db.execute(select(func.count()).select_from(Audit))).scalar_one()
    completed_audits = (
        await db.execute(select(func.count()).select_from(Audit).where(Audit.status == "COMPLETED"))
    ).scalar_one()
    return {
        "registered_users": total_users,
        "verified_users": verified_users,
        "total_audits": total_audits,
        "completed_audits": completed_audits,
        "audit_completion_rate": round(100 * completed_audits / total_audits, 2) if total_audits else None,
    }


@router.get("/feature-flags", dependencies=[Depends(require_super_admin)])
async def list_feature_flags(db: AsyncSession = Depends(get_db)) -> list[dict]:
    result = await db.execute(select(FeatureFlag))
    return [{"key": f.key, "enabled": f.enabled, "config": f.config} for f in result.scalars().all()]


@router.patch("/feature-flags/{key}", dependencies=[Depends(require_super_admin)])
async def update_feature_flag(key: str, enabled: bool, db: AsyncSession = Depends(get_db)) -> dict:
    flag = (await db.execute(select(FeatureFlag).where(FeatureFlag.key == key))).scalar_one_or_none()
    if flag is None:
        raise NotFoundError(f"Feature flag {key!r} not found.")
    flag.enabled = enabled
    await db.commit()
    return {"key": flag.key, "enabled": flag.enabled}
