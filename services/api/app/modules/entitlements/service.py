"""§7-§9, §91, §157 — the entitlement engine.

This module is the single place that decides "can this organization run an
audit?" and is the only code path allowed to create an `Audit` row. The
frontend's own read of `GET /entitlements/audit` is cosmetic (§7); this is
the authoritative, server-side, transactional check.

Race safety has two layers:
  1. `SELECT ... FOR UPDATE` on the organization row serializes concurrent
     entitlement decisions for one org (protects paid-credit double-spend).
  2. The partial unique index `uq_free_entitlement_live` (see
     alembic/versions/0001_initial_schema.py) makes it *structurally
     impossible* for a user to hold two live FREE_LIFETIME rows, even across
     different organizations or when the app-level lock is somehow bypassed.
     A concurrent duplicate INSERT raises IntegrityError, which this module
     catches and turns into AUDIT_PAYMENT_REQUIRED (or ALREADY_RUNNING).

Lifecycle: AVAILABLE -> RESERVED -> CONSUMED (on Audit.COMPLETED) or
RELEASED (on any audit failure). A RELEASED paid credit is reservable again
(its `remaining` was restored); a RELEASED free-lifetime row is *not*
reused — the uniqueness index deliberately excludes RELEASED/EXPIRED from
"live", so retrying inserts a fresh row, which the index still limits to one
at a time.
"""
from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ForbiddenError, PaymentRequiredError
from app.db.base import utcnow
from app.modules.audits.models import Audit, AuditJob, AuditStatus, CURRENT_SCORE_VERSION
from app.modules.auth.models import User
from app.modules.entitlements.models import (
    LIVE_ENTITLEMENT_STATUSES,
    AuditEntitlement,
    EntitlementStatus,
    EntitlementType,
)
from app.modules.organizations.models import Organization
from app.modules.projects.models import Project

PAID_TYPES = (
    EntitlementType.SUBSCRIPTION.value,
    EntitlementType.PURCHASED.value,
    EntitlementType.ADMIN_GRANT.value,
)


class EntitlementDecision:
    def __init__(self, *, can_run: bool, type_: str | None, remaining: int | None, reason: str | None):
        self.can_run = can_run
        self.type = type_
        self.remaining = remaining
        self.reason = reason


async def _has_live_free_entitlement(db: AsyncSession, user_id: uuid.UUID) -> bool:
    result = await db.execute(
        select(AuditEntitlement.id).where(
            AuditEntitlement.user_id == user_id,
            AuditEntitlement.type == EntitlementType.FREE_LIFETIME.value,
            AuditEntitlement.status.in_([s.value for s in LIVE_ENTITLEMENT_STATUSES]),
        )
    )
    return result.first() is not None


async def _find_reservable_paid_entitlement(
    db: AsyncSession, organization_id: uuid.UUID
) -> AuditEntitlement | None:
    result = await db.execute(
        select(AuditEntitlement)
        .where(
            AuditEntitlement.organization_id == organization_id,
            AuditEntitlement.type.in_(PAID_TYPES),
            AuditEntitlement.status.in_(
                [EntitlementStatus.AVAILABLE.value, EntitlementStatus.RELEASED.value]
            ),
            AuditEntitlement.remaining > 0,
        )
        .order_by(AuditEntitlement.created_at.asc())
        .with_for_update()
        .limit(1)
    )
    return result.scalar_one_or_none()


async def get_entitlement_status(db: AsyncSession, *, organization_id: uuid.UUID, user: User) -> EntitlementDecision:
    """Read-only status for §91 `GET /entitlements/audit` — informational
    only, never used to authorize an audit creation.
    """
    paid = await _find_reservable_paid_entitlement(db, organization_id)
    if paid is not None:
        return EntitlementDecision(can_run=True, type_=paid.type, remaining=paid.remaining, reason=None)

    if not user.is_email_verified:
        return EntitlementDecision(can_run=False, type_=None, remaining=None, reason="EMAIL_NOT_VERIFIED")

    if await _has_live_free_entitlement(db, user.id):
        return EntitlementDecision(
            can_run=False, type_=None, remaining=0, reason="PAYMENT_REQUIRED"
        )

    return EntitlementDecision(
        can_run=True, type_=EntitlementType.FREE_LIFETIME.value, remaining=1, reason=None
    )


# §5 free crawl limit, and the M1 default for any paid credit (single-audit
# purchase). A plan-specific limit (§80 `crawl_url_limit`) supersedes this
# once subscriptions are wired in M2 — tracked as a TODO rather than plumbed
# through now, since M1's only paid flow is the single-audit purchase.
FREE_MAX_URLS = 500
PAID_MAX_URLS = 2000


async def create_audit_with_entitlement(
    db: AsyncSession,
    *,
    organization: Organization,
    user: User,
    project: Project,
    requested_max_urls: int | None = None,
) -> Audit:
    """The single authorized path to create an Audit row (§157).

    Runs inside the caller's existing transaction/session; callers must
    await `db.commit()` (or let the request-scoped session do so) after this
    returns, and must be prepared for PaymentRequiredError on a lost race.

    `requested_max_urls` is a client hint only — it is capped by the plan
    limit implied by whichever entitlement actually pays for this audit, and
    server-side crawl-URL limits are the authority, never the client's ask.
    """
    if not user.is_email_verified:
        raise ForbiddenError("Verify your email before running an audit.")

    # Layer 1: serialize entitlement decisions for this organization so two
    # concurrent requests can't both see (and both spend) the last paid
    # credit. Free-lifetime races are additionally covered by layer 2 below
    # regardless of this lock, since that entitlement is keyed by user, not
    # by organization.
    await db.execute(select(Organization.id).where(Organization.id == organization.id).with_for_update())

    paid_entitlement = await _find_reservable_paid_entitlement(db, organization.id)

    plan_cap = PAID_MAX_URLS if paid_entitlement is not None else FREE_MAX_URLS
    max_urls = min(requested_max_urls, plan_cap) if requested_max_urls else plan_cap

    audit = Audit(
        organization_id=organization.id,
        project_id=project.id,
        requested_by=user.id,
        status=AuditStatus.QUEUED.value,
        max_urls=max_urls,
        score_version=CURRENT_SCORE_VERSION,
    )
    db.add(audit)
    await db.flush()

    if paid_entitlement is not None:
        # NOTE: this correctly models M1's only paid flow — one row per
        # single-audit purchase, quantity=1. A future multi-audit
        # subscription quota (quantity>1, shared across many audits) needs a
        # different shape (a standing AVAILABLE "grant" row plus a separate
        # CONSUMED "spend" row per audit) since one row's single `audit_id`
        # FK can't represent more than one in-flight reservation at a time.
        paid_entitlement.remaining -= 1
        paid_entitlement.status = EntitlementStatus.RESERVED.value
        paid_entitlement.reserved_at = utcnow()
        paid_entitlement.audit_id = audit.id
        await db.flush()
    else:
        if await _has_live_free_entitlement(db, user.id):
            # Undo this request's not-yet-committed Audit row before
            # surfacing the error — the session would roll back on close
            # regardless, but doing it explicitly here keeps the invariant
            # ("no Audit row survives without a paired entitlement") visible
            # at the call site rather than relying on session-teardown
            # behavior.
            await db.rollback()
            raise PaymentRequiredError("Your free audit has already been used.")

        entitlement = AuditEntitlement(
            organization_id=organization.id,
            user_id=user.id,
            type=EntitlementType.FREE_LIFETIME.value,
            status=EntitlementStatus.RESERVED.value,
            audit_id=audit.id,
            quantity=1,
            remaining=0,
            source="SIGNUP_BONUS",
            reserved_at=utcnow(),
        )
        db.add(entitlement)

        # Layer 2: the actual race-proof guarantee. If a concurrent request
        # already committed a live FREE_LIFETIME row for this user (possibly
        # in a different organization), this flush hits the partial unique
        # index and raises IntegrityError.
        try:
            await db.flush()
        except IntegrityError as exc:
            await db.rollback()
            raise PaymentRequiredError("Your free audit has already been used.") from exc

    job = AuditJob(audit_id=audit.id, status=AuditStatus.QUEUED.value)
    db.add(job)

    await db.commit()
    await db.refresh(audit)
    return audit


async def consume_entitlement_for_audit(db: AsyncSession, audit: Audit) -> None:
    """Called only when an audit transitions to COMPLETED (§4, §157).

    Deliberately does NOT commit — the caller (app/workers/tasks/crawl.py)
    mutates the Audit/AuditJob status in the same call and commits once, so
    "audit COMPLETED" and "entitlement CONSUMED" land atomically. Two
    separate commits would leave a window where a crash (or, in tests, a
    poller that wakes the instant the first commit lands) could observe a
    COMPLETED audit whose entitlement is still RESERVED forever.
    """
    entitlement = (
        await db.execute(select(AuditEntitlement).where(AuditEntitlement.audit_id == audit.id))
    ).scalar_one_or_none()
    if entitlement is None:
        return

    entitlement.status = (
        EntitlementStatus.CONSUMED.value if entitlement.remaining <= 0 else EntitlementStatus.AVAILABLE.value
    )
    entitlement.consumed_at = utcnow()

    if entitlement.type == EntitlementType.FREE_LIFETIME.value:
        user = (await db.execute(select(User).where(User.id == entitlement.user_id))).scalar_one_or_none()
        if user is not None:
            user.free_audit_used_at = utcnow()


async def release_entitlement_for_audit(db: AsyncSession, audit: Audit) -> None:
    """Called when an audit fails for a qualifying reason (§4, §30, §119) —
    restores the credit (or, for free-lifetime, frees the user to retry via
    a brand-new row next time, per the module docstring above).

    Also does not commit, for the same atomicity reason as
    `consume_entitlement_for_audit` above — see app/workers/tasks/crawl.py's
    `_fail_audit`, which commits this together with the audit/job's FAILED
    status in one transaction.
    """
    entitlement = (
        await db.execute(select(AuditEntitlement).where(AuditEntitlement.audit_id == audit.id))
    ).scalar_one_or_none()
    if entitlement is None:
        return

    entitlement.remaining += 1
    entitlement.status = EntitlementStatus.RELEASED.value
