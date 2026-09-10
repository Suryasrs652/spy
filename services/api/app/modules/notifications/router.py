from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user
from app.db.session import get_db
from app.modules.auth.models import User
from app.modules.notifications import service
from app.modules.notifications.schemas import MarkAllReadOut, NotificationListOut, NotificationOut

router = APIRouter(prefix="/notifications", tags=["notifications"])


@router.get("", response_model=NotificationListOut)
async def list_notifications(
    limit: int = 50,
    offset: int = 0,
    unread_only: bool = False,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> NotificationListOut:
    notifications = await service.list_notifications(
        db, user_id=user.id, limit=limit, offset=offset, unread_only=unread_only
    )
    unread_count = await service.count_unread(db, user_id=user.id)
    return NotificationListOut(
        notifications=[NotificationOut.model_validate(n) for n in notifications], unread_count=unread_count
    )


@router.post("/{notification_id}/read", response_model=NotificationOut)
async def mark_notification_read(
    notification_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> NotificationOut:
    notification = await service.mark_read(db, user_id=user.id, notification_id=notification_id)
    return NotificationOut.model_validate(notification)


@router.post("/read-all", response_model=MarkAllReadOut)
async def mark_all_notifications_read(
    user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> MarkAllReadOut:
    marked = await service.mark_all_read(db, user_id=user.id)
    return MarkAllReadOut(marked_read=marked)
