"""§96/§128/§129 admin endpoints — real SUPER_ADMIN session auth (see
`app.core.deps.require_super_admin`), not the M1 shared-token placeholder.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import require_super_admin
from app.core.errors import NotFoundError
from app.db.base import utcnow
from app.db.session import get_db
from app.modules.admin import service
from app.modules.admin.models import AuditLog, FeatureFlag
from app.modules.audits.models import Audit
from app.modules.auth.models import User
from app.modules.organizations.models import Organization

router = APIRouter(prefix="/admin", tags=["admin"], dependencies=[Depends(require_super_admin)])


@router.get("/users")
async def list_users(db: AsyncSession = Depends(get_db), limit: int = 50, offset: int = 0) -> list[dict]:
    result = await db.execute(select(User).order_by(User.created_at.desc()).limit(limit).offset(offset))
    return [
        {"id": str(u.id), "email": u.email, "status": u.status, "email_verified": u.is_email_verified,
         "created_at": u.created_at.isoformat()}
        for u in result.scalars().all()
    ]


@router.get("/organizations")
async def list_organizations(db: AsyncSession = Depends(get_db), limit: int = 50, offset: int = 0) -> list[dict]:
    result = await db.execute(select(Organization).order_by(Organization.created_at.desc()).limit(limit).offset(offset))
    return [{"id": str(o.id), "name": o.name, "slug": o.slug} for o in result.scalars().all()]


@router.get("/audits")
async def list_all_audits(db: AsyncSession = Depends(get_db), limit: int = 50, offset: int = 0) -> list[dict]:
    result = await db.execute(select(Audit).order_by(Audit.created_at.desc()).limit(limit).offset(offset))
    return [
        {"id": str(a.id), "status": a.status, "spy_score": float(a.spy_score) if a.spy_score is not None else None,
         "failure_code": a.failure_code, "created_at": a.created_at.isoformat()}
        for a in result.scalars().all()
    ]


@router.get("/overview")
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


@router.get("/revenue")
async def revenue(days: int = 30, db: AsyncSession = Depends(get_db)) -> dict:
    return await service.get_revenue_summary(db, days=days)


@router.get("/queue")
async def queue_health(db: AsyncSession = Depends(get_db)) -> dict:
    return await service.get_queue_health(db)


@router.get("/errors")
async def error_summary(days: int = 7, db: AsyncSession = Depends(get_db)) -> dict:
    return await service.get_error_summary(db, days=days)


@router.get("/audit-logs")
async def audit_logs(limit: int = 100, offset: int = 0, db: AsyncSession = Depends(get_db)) -> list[dict]:
    logs = await service.list_audit_logs(db, limit=limit, offset=offset)
    return [
        {
            "id": log.id, "organization_id": str(log.organization_id) if log.organization_id else None,
            "user_id": str(log.user_id) if log.user_id else None, "action": log.action,
            "entity_type": log.entity_type, "entity_id": log.entity_id,
            "metadata": log.metadata_json, "created_at": log.created_at.isoformat(),
        }
        for log in logs
    ]


@router.get("/feature-flags")
async def list_feature_flags(db: AsyncSession = Depends(get_db)) -> list[dict]:
    result = await db.execute(select(FeatureFlag))
    return [{"key": f.key, "enabled": f.enabled, "config": f.config} for f in result.scalars().all()]


@router.patch("/feature-flags/{key}")
async def update_feature_flag(
    key: str, enabled: bool, admin: User = Depends(require_super_admin), db: AsyncSession = Depends(get_db)
) -> dict:
    flag = (await db.execute(select(FeatureFlag).where(FeatureFlag.key == key))).scalar_one_or_none()
    if flag is None:
        raise NotFoundError(f"Feature flag {key!r} not found.")
    flag.enabled = enabled
    db.add(
        AuditLog(
            organization_id=None, user_id=admin.id, action="feature_flag.update",
            entity_type="feature_flag", entity_id=key, metadata_json={"enabled": enabled},
            created_at=utcnow(),
        )
    )
    await db.commit()
    return {"key": flag.key, "enabled": flag.enabled}
