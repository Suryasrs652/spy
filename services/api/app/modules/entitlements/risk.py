"""§6 free-audit abuse prevention.

Layered, low-friction risk signals — never a single-signal block, never
invasive device fingerprinting, and never a hard block purely on shared
office/agency IPs. The score only ever affects the FREE_LIFETIME path; paid
entitlements are never risk-scored.
"""
from __future__ import annotations

import hashlib
import uuid
from datetime import timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db.base import utcnow
from app.modules.admin.models import AuditLog

# A tiny illustrative denylist — production would use a maintained disposable-
# domain list (e.g. updated from a public dataset), not this hard-coded set.
_DISPOSABLE_EMAIL_DOMAINS = {
    "mailinator.com", "10minutemail.com", "tempmail.com", "guerrillamail.com",
    "yopmail.com", "trashmail.com",
}

RISK_ALLOW_THRESHOLD = 30
RISK_BLOCK_THRESHOLD = 70


def hash_ip(ip: str) -> str:
    settings = get_settings()
    return hashlib.sha256(f"{settings.auth_secret}:{ip}".encode()).hexdigest()


async def compute_signup_risk_score(db: AsyncSession, *, email: str, ip_hash: str) -> int:
    score = 0

    domain = email.rsplit("@", 1)[-1].lower()
    if domain in _DISPOSABLE_EMAIL_DOMAINS:
        score += 40

    since = utcnow() - timedelta(hours=24)
    recent_signups = (
        await db.execute(
            select(func.count()).select_from(AuditLog).where(
                AuditLog.action == "user.signup",
                AuditLog.ip_hash == ip_hash,
                AuditLog.created_at >= since,
            )
        )
    ).scalar_one()
    # A handful of signups from one office/agency IP is normal; only a burst
    # is suspicious (§6: never hard-block a shared IP on its own).
    if recent_signups >= 5:
        score += 30
    elif recent_signups >= 3:
        score += 15

    return min(score, 100)


async def has_prior_audit_for_domain(db: AsyncSession, *, canonical_origin: str, user_id: uuid.UUID) -> bool:
    """True if a *different* user has already run a completed audit against
    this exact domain — a signal (not a hard rule) that this free audit
    request may be a repeat attempt under a new account.
    """
    from app.modules.audits.models import Audit, AuditStatus
    from app.modules.projects.models import Project

    result = await db.execute(
        select(func.count())
        .select_from(Audit)
        .join(Project, Project.id == Audit.project_id)
        .where(
            Project.canonical_origin == canonical_origin,
            Audit.status == AuditStatus.COMPLETED.value,
            Audit.requested_by != user_id,
        )
    )
    return (result.scalar_one()) > 0
