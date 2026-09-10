"""§134 notifications — in-app inbox + best-effort email delivery, against
real Postgres. Email delivery itself (MailHog) is exercised for real by
existing auth-flow tests (signup/verify/reset all call send_email); these
tests focus on the notification row lifecycle and the audit/billing hooks
that create one.
"""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select

from app.modules.notifications.models import Notification, NotificationType
from app.modules.notifications.service import (
    count_unread,
    create_notification,
    list_notifications,
    mark_all_read,
    mark_read,
)
from tests.conftest import unique_email


@pytest.mark.asyncio
async def test_create_and_list_notification(db, verified_user):
    user, org_id, _token = verified_user

    notification = await create_notification(
        db, user_id=user.id, organization_id=org_id, type=NotificationType.AUDIT_COMPLETED,
        title="Your audit is ready", body="Score: 92/100", link_path="/audits/123",
    )
    assert notification.id is not None
    assert notification.read_at is None

    notifications = await list_notifications(db, user_id=user.id)
    assert len(notifications) == 1
    assert notifications[0].title == "Your audit is ready"


@pytest.mark.asyncio
async def test_unread_count_and_mark_read(db, verified_user):
    user, org_id, _token = verified_user

    n1 = await create_notification(
        db, user_id=user.id, organization_id=org_id, type=NotificationType.AUDIT_COMPLETED,
        title="A", body="a",
    )
    await create_notification(
        db, user_id=user.id, organization_id=org_id, type=NotificationType.AUDIT_FAILED,
        title="B", body="b",
    )

    assert await count_unread(db, user_id=user.id) == 2

    read = await mark_read(db, user_id=user.id, notification_id=n1.id)
    assert read.read_at is not None
    assert await count_unread(db, user_id=user.id) == 1

    # Marking again is a no-op, not an error.
    read_again = await mark_read(db, user_id=user.id, notification_id=n1.id)
    assert read_again.read_at == read.read_at


@pytest.mark.asyncio
async def test_mark_all_read(db, verified_user):
    user, org_id, _token = verified_user
    for i in range(3):
        await create_notification(
            db, user_id=user.id, organization_id=org_id, type=NotificationType.AUDIT_COMPLETED,
            title=f"N{i}", body="body",
        )

    marked = await mark_all_read(db, user_id=user.id)
    assert marked == 3
    assert await count_unread(db, user_id=user.id) == 0

    # A second call has nothing left to mark.
    assert await mark_all_read(db, user_id=user.id) == 0


@pytest.mark.asyncio
async def test_notifications_are_scoped_to_the_owning_user(db, verified_user):
    user_a, org_a, _ = verified_user

    from app.modules.auth import service as auth_service

    user_b, org_b = await auth_service.signup(
        db, email=unique_email(), password="correct horse battery staple", name=None
    )

    await create_notification(
        db, user_id=user_a.id, organization_id=org_a, type=NotificationType.AUDIT_COMPLETED,
        title="For A", body="a",
    )

    assert len(await list_notifications(db, user_id=user_a.id)) == 1
    assert len(await list_notifications(db, user_id=user_b.id)) == 0


@pytest.mark.asyncio
async def test_mark_read_rejects_another_users_notification(db, verified_user):
    from app.core.errors import NotFoundError
    from app.modules.auth import service as auth_service

    user_a, org_a, _ = verified_user
    user_b, _org_b = await auth_service.signup(
        db, email=unique_email(), password="correct horse battery staple", name=None
    )

    notification = await create_notification(
        db, user_id=user_a.id, organization_id=org_a, type=NotificationType.AUDIT_COMPLETED,
        title="For A", body="a",
    )

    with pytest.raises(NotFoundError):
        await mark_read(db, user_id=user_b.id, notification_id=notification.id)


@pytest.mark.asyncio
async def test_full_commercial_loop_creates_audit_completed_notification(client, db, auth_headers):
    """Integration check that the crawl pipeline's success path actually
    calls notify_audit_completed (app/workers/tasks/crawl.py) end to end,
    not just that the service function works in isolation.
    """
    from datetime import datetime, timezone

    from app.core.security import issue_access_token
    from app.modules.audits.models import AuditStatus
    from app.modules.auth.models import User
    from tests.conftest import wait_for_audit_terminal

    email = unique_email()
    signup_resp = await client.post(
        "/api/v1/auth/signup", json={"email": email, "password": "correct horse battery staple"}
    )
    assert signup_resp.status_code == 201
    org_id = signup_resp.json()["organization_id"]
    user_id = signup_resp.json()["user_id"]

    user = (await db.execute(select(User).where(User.id == uuid.UUID(user_id)))).scalar_one()
    user.email_verified_at = datetime.now(timezone.utc)
    await db.commit()

    token = issue_access_token(user_id, org_id)
    headers = auth_headers(token, org_id)

    project_resp = await client.post(
        "/api/v1/projects", json={"name": "Test Site", "url": "https://example.com"}, headers=headers
    )
    project_id = project_resp.json()["id"]

    audit_resp = await client.post("/api/v1/audits", json={"project_id": project_id}, headers=headers)
    audit_id = uuid.UUID(audit_resp.json()["id"])

    audit = await wait_for_audit_terminal(db, audit_id, timeout=60)
    assert audit.status == AuditStatus.COMPLETED.value

    notifications = (
        await db.execute(select(Notification).where(Notification.user_id == uuid.UUID(user_id)))
    ).scalars().all()
    assert any(n.type == NotificationType.AUDIT_COMPLETED.value for n in notifications)

    list_resp = await client.get("/api/v1/notifications", headers=headers)
    assert list_resp.status_code == 200
    body = list_resp.json()
    assert body["unread_count"] >= 1
    assert any(n["type"] == "AUDIT_COMPLETED" for n in body["notifications"])
