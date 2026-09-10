"""§60 users table."""
from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import Boolean, DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPKMixin


class UserStatus(StrEnum):
    ACTIVE = "ACTIVE"
    SUSPENDED = "SUSPENDED"
    DELETED = "DELETED"


class User(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(320), unique=True, nullable=False, index=True)
    password_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    email_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=UserStatus.ACTIVE.value
    )
    free_audit_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Set when the user's first identity was Google OAuth (oauth-upsert path).
    google_sub: Mapped[str | None] = mapped_column(String(255), unique=True, nullable=True)

    # §128/§129 — platform-wide admin, distinct from any org's OWNER/ADMIN
    # role (those are tenant-scoped; this is not). Never settable through a
    # public API — only ever flipped directly in the DB/by another admin.
    is_super_admin: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    @property
    def is_email_verified(self) -> bool:
        return self.email_verified_at is not None
