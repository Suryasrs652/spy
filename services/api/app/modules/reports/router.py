from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import AuthContext, require_role
from app.db.session import get_db
from app.modules.organizations.models import ROLE_CAN_VIEW
from app.modules.reports import service

router = APIRouter(prefix="/audits", tags=["reports"])


@router.get("/{audit_id}/report/download")
async def download_report(
    audit_id: uuid.UUID,
    ctx: AuthContext = Depends(require_role(*ROLE_CAN_VIEW)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    report = await service.get_latest_report(db, organization_id=ctx.organization_id, audit_id=audit_id)
    url = await service.get_download_url(db, organization_id=ctx.organization_id, report_id=report.id)
    # A signed, short-lived URL — the client redirects the browser to it
    # rather than the API streaming the PDF itself (§108).
    return {"url": url, "expires_in_seconds": 600}
