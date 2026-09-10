"""§134 — notification creation, delivery, and the in-app inbox.

Every `notify_*` helper is called *after* the triggering transaction has
already committed (mirrors how `_send_verification_email` follows signup's
commit in auth/service.py) — a notification is a side effect of a fact
that already happened, never a participant in the transaction that decided
the fact. Email delivery failure must never lose the in-app notification or
vice versa, so the row is written first and the email is best-effort.
"""
from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.email import send_email
from app.core.errors import NotFoundError
from app.db.base import utcnow
from app.modules.notifications.models import Notification, NotificationType

_EMAIL_SUBJECTS = {
    NotificationType.AUDIT_COMPLETED: "Your Spy audit is ready",
    NotificationType.AUDIT_FAILED: "Your Spy audit couldn't complete",
    NotificationType.PURCHASE_SUCCEEDED: "Your Spy purchase was successful",
    NotificationType.PURCHASE_FAILED: "Your Spy purchase failed",
}


async def create_notification(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    organization_id: uuid.UUID,
    type: NotificationType,
    title: str,
    body: str,
    link_path: str | None = None,
    email_to: str | None = None,
) -> Notification:
    notification = Notification(
        user_id=user_id, organization_id=organization_id,
        type=type.value, title=title, body=body, link_path=link_path,
    )
    db.add(notification)
    await db.commit()
    await db.refresh(notification)

    if email_to:
        await send_email(to=email_to, subject=_EMAIL_SUBJECTS.get(type, title), body=body)

    return notification


async def notify_audit_completed(db: AsyncSession, *, audit, requester_email: str) -> None:
    score_text = f"{audit.spy_score:.0f}" if audit.spy_score is not None else "n/a"
    await create_notification(
        db,
        user_id=audit.requested_by, organization_id=audit.organization_id,
        type=NotificationType.AUDIT_COMPLETED,
        title="Your audit is ready",
        body=f"Your Spy Score audit finished with a score of {score_text}/100.",
        link_path=f"/audits/{audit.id}",
        email_to=requester_email,
    )


async def notify_audit_failed(db: AsyncSession, *, audit, requester_email: str) -> None:
    reason = audit.failure_message or "An unexpected error occurred."
    await create_notification(
        db,
        user_id=audit.requested_by, organization_id=audit.organization_id,
        type=NotificationType.AUDIT_FAILED,
        title="Your audit couldn't complete",
        body=f"Your Spy audit failed: {reason} Your credit has been returned — you can try again.",
        link_path=f"/audits/{audit.id}",
        email_to=requester_email,
    )


async def notify_purchase_succeeded(db: AsyncSession, *, purchase, owner_user_id: uuid.UUID, owner_email: str) -> None:
    amount = purchase.amount_minor / 100
    await create_notification(
        db,
        user_id=owner_user_id, organization_id=purchase.organization_id,
        type=NotificationType.PURCHASE_SUCCEEDED,
        title="Purchase successful",
        body=f"Your payment of {purchase.currency} {amount:.2f} was successful and your credit is ready to use.",
        link_path="/billing",
        email_to=owner_email,
    )


async def notify_purchase_failed(db: AsyncSession, *, purchase, owner_user_id: uuid.UUID, owner_email: str) -> None:
    amount = purchase.amount_minor / 100
    await create_notification(
        db,
        user_id=owner_user_id, organization_id=purchase.organization_id,
        type=NotificationType.PURCHASE_FAILED,
        title="Purchase failed",
        body=f"Your payment of {purchase.currency} {amount:.2f} did not go through. No credit was granted.",
        link_path="/billing",
        email_to=owner_email,
    )


async def list_notifications(
    db: AsyncSession, *, user_id: uuid.UUID, limit: int = 50, offset: int = 0, unread_only: bool = False
) -> list[Notification]:
    query = select(Notification).where(Notification.user_id == user_id)
    if unread_only:
        query = query.where(Notification.read_at.is_(None))
    query = query.order_by(Notification.created_at.desc()).limit(limit).offset(offset)
    return list((await db.execute(query)).scalars().all())


async def count_unread(db: AsyncSession, *, user_id: uuid.UUID) -> int:
    result = await db.execute(
        select(func.count()).select_from(Notification).where(
            Notification.user_id == user_id, Notification.read_at.is_(None)
        )
    )
    return result.scalar_one()


async def mark_read(db: AsyncSession, *, user_id: uuid.UUID, notification_id: uuid.UUID) -> Notification:
    notification = (
        await db.execute(
            select(Notification).where(Notification.id == notification_id, Notification.user_id == user_id)
        )
    ).scalar_one_or_none()
    if notification is None:
        raise NotFoundError("Notification not found.")
    if notification.read_at is None:
        notification.read_at = utcnow()
        await db.commit()
    return notification


async def mark_all_read(db: AsyncSession, *, user_id: uuid.UUID) -> int:
    result = await db.execute(
        select(Notification).where(Notification.user_id == user_id, Notification.read_at.is_(None))
    )
    unread = list(result.scalars().all())
    now = utcnow()
    for n in unread:
        n.read_at = now
    if unread:
        await db.commit()
    return len(unread)
