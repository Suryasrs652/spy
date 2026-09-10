"""§109 self-service account deletion — anonymize + soft-delete, against
real Postgres. A hard DELETE of the user row is deliberately never
attempted (Audit.requested_by has no ON DELETE CASCADE), so these tests
assert on the anonymization contract instead.
"""
from __future__ import annotations

import pytest
from sqlalchemy import select

from app.core.errors import ConflictError
from app.modules.auth.models import User, UserStatus
from app.modules.auth.service import delete_own_account
from tests.conftest import unique_email


@pytest.mark.asyncio
async def test_delete_own_account_anonymizes_the_user_row(db, verified_user):
    user, _org_id, _token = verified_user
    original_id = user.id
    original_email = user.email

    await delete_own_account(db, user=user)

    refreshed = (await db.execute(select(User).where(User.id == original_id))).scalar_one()
    assert refreshed.status == UserStatus.DELETED.value
    assert refreshed.password_hash is None
    assert refreshed.google_sub is None
    assert refreshed.email.endswith("@deleted.invalid")
    assert refreshed.email != original_email


@pytest.mark.asyncio
async def test_deleted_account_cannot_authenticate(db, client, verified_user):
    user, _org_id, _token = verified_user
    email = user.email

    await delete_own_account(db, user=user)

    resp = await client.post(
        "/api/v1/auth/signup", json={"email": email, "password": "correct horse battery staple"}
    )
    # The old email is free again (it was anonymized), so signup succeeds —
    # proving the deletion actually released the address rather than merely
    # blocking it.
    assert resp.status_code == 201


@pytest.mark.asyncio
async def test_delete_own_account_blocked_when_sole_owner_of_multi_member_org(db, verified_user):
    from app.modules.auth import service as auth_service
    from app.modules.organizations.models import OrganizationMember, OrgRole

    user, org_id, _token = verified_user
    user_id = user.id
    other_user, _other_org = await auth_service.signup(
        db, email=unique_email(), password="correct horse battery staple", name=None
    )
    db.add(OrganizationMember(organization_id=org_id, user_id=other_user.id, role=OrgRole.ANALYST.value))
    await db.commit()
    await db.refresh(user)

    with pytest.raises(ConflictError):
        await delete_own_account(db, user=user)

    still_active = (await db.execute(select(User).where(User.id == user_id))).scalar_one()
    assert still_active.status == UserStatus.ACTIVE.value


@pytest.mark.asyncio
async def test_delete_own_account_via_http(client, db, verified_user, auth_headers):
    user, org_id, token = verified_user

    resp = await client.delete("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    assert resp.json()["deleted"] is True

    me_resp = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me_resp.status_code == 401, "a deleted account's existing access token must stop working"
