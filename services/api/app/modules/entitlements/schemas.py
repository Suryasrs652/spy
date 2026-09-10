"""§91 GET /entitlements/audit response shape."""
from __future__ import annotations

from pydantic import BaseModel


class EntitlementAuditOut(BaseModel):
    can_run: bool
    type: str | None = None
    remaining: int | None = None
    reason: str | None = None
