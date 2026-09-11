"""§60 users table.

Spy is self-hosted and single-user, so there is exactly one row here —
the local workspace owner (app/core/local_workspace.py). The table stays
because every tenant table's `organization_id` chain ends at it, and
because putting real multi-user auth back should be a change to
local_workspace rather than a schema-wide migration. The
credential/entitlement columns (password_hash, google_sub,
free_audit_used_at, is_super_admin) went away with sign-in and billing —
see migration 0011.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPKMixin


class UserStatus(StrEnum):
    ACTIVE = "ACTIVE"
    SUSPENDED = "SUSPENDED"
    DELETED = "DELETED"


class User(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(320), unique=True, nullable=False, index=True)
    email_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=UserStatus.ACTIVE.value
    )

    @property
    def is_email_verified(self) -> bool:
        return self.email_verified_at is not None
