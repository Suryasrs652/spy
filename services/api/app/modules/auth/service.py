"""§15, §60, §105 — signup, verification, credential checks.

FastAPI is the sole owner of the users table and the only place Argon2id
hashing happens (§105). Auth.js in apps/web never sees a password hash; it
calls the internal endpoints backed by `verify_credentials` / `oauth_upsert`
below and gets back a user id it can put in a session.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import jwt
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.email import (
    password_reset_email_body,
    send_email,
    verification_email_body,
)
from app.core.errors import ConflictError, NotFoundError, UnauthenticatedError, ValidationAppError
from app.core.security import (
    DUMMY_PASSWORD_HASH,
    decode_jwt,
    hash_password,
    issue_jwt,
    verify_password,
)
from app.modules.auth.models import User, UserStatus
from app.modules.organizations.service import (
    create_organization_with_owner,
    list_user_organizations,
)

# §109 — a real (non-routable) TLD, never valid to send mail to, so an
# anonymized row can never accidentally collide with or reactivate as a
# real address later.
_DELETED_EMAIL_DOMAIN = "deleted.invalid"


async def get_user_by_email(db: AsyncSession, email: str) -> User | None:
    result = await db.execute(select(User).where(User.email == email.lower()))
    return result.scalar_one_or_none()


async def signup(db: AsyncSession, *, email: str, password: str, name: str | None) -> tuple[User, uuid.UUID]:
    email = email.lower().strip()
    existing = await get_user_by_email(db, email)
    if existing is not None:
        raise ConflictError("An account with this email already exists.")

    user = User(email=email, password_hash=hash_password(password))
    db.add(user)
    await db.flush()

    org_name = name.strip() if name else email.split("@")[0]
    org = await create_organization_with_owner(
        db, name=f"{org_name}'s Workspace", owner_user_id=user.id
    )

    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise ConflictError("An account with this email already exists.") from exc

    await _send_verification_email(user)
    return user, org.id


async def _send_verification_email(user: User) -> None:
    settings = get_settings()
    token = issue_jwt(subject=str(user.id), token_type="email_verify", ttl=timedelta(hours=24))
    verify_url = f"{settings.web_base_url}/verify-email?token={token}"
    await send_email(
        to=user.email, subject="Verify your Spy account", body=verification_email_body(verify_url)
    )


async def resend_verification_email(db: AsyncSession, *, email: str) -> None:
    user = await get_user_by_email(db, email)
    if user is None or user.is_email_verified:
        return  # never reveal whether the account exists (§150 privacy)
    await _send_verification_email(user)


async def verify_email(db: AsyncSession, *, token: str) -> User:
    try:
        payload = decode_jwt(token, expected_type="email_verify")
    except jwt.InvalidTokenError as exc:
        raise ValidationAppError("This verification link is invalid or has expired.") from exc

    user_id = uuid.UUID(payload["sub"])
    user = (await db.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
    if user is None:
        raise NotFoundError("Account not found.")

    if user.email_verified_at is None:
        user.email_verified_at = datetime.now(timezone.utc)
        await db.commit()
    return user


async def request_password_reset(db: AsyncSession, *, email: str) -> None:
    user = await get_user_by_email(db, email)
    if user is None:
        return  # do not reveal account existence
    settings = get_settings()
    token = issue_jwt(subject=str(user.id), token_type="password_reset", ttl=timedelta(hours=1))
    reset_url = f"{settings.web_base_url}/reset-password?token={token}"
    await send_email(
        to=user.email, subject="Reset your Spy password", body=password_reset_email_body(reset_url)
    )


async def reset_password(db: AsyncSession, *, token: str, new_password: str) -> None:
    try:
        payload = decode_jwt(token, expected_type="password_reset")
    except jwt.InvalidTokenError as exc:
        raise ValidationAppError("This reset link is invalid or has expired.") from exc

    user_id = uuid.UUID(payload["sub"])
    user = (await db.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
    if user is None:
        raise NotFoundError("Account not found.")

    user.password_hash = hash_password(new_password)
    await db.commit()


async def verify_credentials(db: AsyncSession, *, email: str, password: str) -> User:
    user = await get_user_by_email(db, email)
    if user is None or not user.password_hash:
        # Constant-shape failure whether the account exists or not.
        verify_password(password, DUMMY_PASSWORD_HASH)
        raise UnauthenticatedError("Invalid email or password.")

    if not verify_password(password, user.password_hash):
        raise UnauthenticatedError("Invalid email or password.")

    if user.status != UserStatus.ACTIVE.value:
        raise UnauthenticatedError("This account is not active.")

    return user


async def oauth_upsert(db: AsyncSession, *, email: str, google_sub: str, name: str | None) -> User:
    """Find-or-create the user behind a Google login (§15).

    Links by google_sub first, falling back to email (so a user who signed
    up with a password can later also sign in with the same Google account
    without creating a duplicate).
    """
    email = email.lower().strip()

    result = await db.execute(select(User).where(User.google_sub == google_sub))
    user = result.scalar_one_or_none()
    if user is not None:
        return user

    user = await get_user_by_email(db, email)
    if user is not None:
        user.google_sub = google_sub
        if user.email_verified_at is None:
            user.email_verified_at = datetime.now(timezone.utc)  # Google already verified it
        await db.commit()
        return user

    user = User(email=email, google_sub=google_sub, email_verified_at=datetime.now(timezone.utc))
    db.add(user)
    await db.flush()

    org_name = name.strip() if name else email.split("@")[0]
    await create_organization_with_owner(db, name=f"{org_name}'s Workspace", owner_user_id=user.id)

    await db.commit()
    return user


async def default_organization_id(db: AsyncSession, user_id: uuid.UUID) -> uuid.UUID:
    orgs = await list_user_organizations(db, user_id)
    if not orgs:
        raise NotFoundError("No organization found for this user.")
    return orgs[0].id


async def delete_own_account(db: AsyncSession, *, user: User) -> None:
    """§109 self-service account deletion.

    The user row is never hard-deleted — `Audit.requested_by` and several
    other tables reference it with no ON DELETE CASCADE (deliberately: an
    audit's history must survive the requester's account), so a hard delete
    would fail a foreign-key constraint anyway. Instead this anonymizes the
    row (Argon2id hash dropped, email replaced with a non-routable
    placeholder, OAuth link dropped) and flips status to DELETED, which
    `verify_credentials`/`get_current_user` already treat as unusable.

    Blocked when the user is the OWNER of an organization that has other
    members — deleting them would silently strand those teammates with no
    owner. They must transfer ownership or remove the other members first.
    """
    from sqlalchemy import func, select

    from app.modules.billing.models import Subscription, SubscriptionStatus
    from app.modules.organizations.models import OrganizationMember

    owned_orgs = [
        org for org in await list_user_organizations(db, user.id)
        if org.owner_user_id == user.id
    ]
    for org in owned_orgs:
        member_count = (
            await db.execute(
                select(func.count()).select_from(OrganizationMember).where(
                    OrganizationMember.organization_id == org.id
                )
            )
        ).scalar_one()
        if member_count > 1:
            raise ConflictError(
                "You own a workspace with other members. Transfer ownership or remove the other "
                "members before deleting your account."
            )

    for org in owned_orgs:
        result = await db.execute(
            select(Subscription).where(
                Subscription.organization_id == org.id, Subscription.status == SubscriptionStatus.ACTIVE.value
            )
        )
        for sub in result.scalars().all():
            sub.status = SubscriptionStatus.CANCELLED.value
            sub.cancel_at_period_end = False

    user.email = f"deleted-{user.id.hex}@{_DELETED_EMAIL_DOMAIN}"
    user.password_hash = None
    user.google_sub = None
    user.status = UserStatus.DELETED.value
    await db.commit()
