"""§99 Idempotency-Key support for audit creation, purchases and reports.

This is defense-in-depth on top of the endpoint's own correctness (the free
audit's real protection is the DB-level partial unique index in the
entitlements module; idempotency keys additionally protect against a client
retrying a POST after a dropped response and accidentally double-submitting).
"""
from __future__ import annotations

import uuid
from typing import Any, Awaitable, Callable

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.admin.models import IdempotencyKey


def _storage_key(organization_id: uuid.UUID, endpoint: str, idempotency_key: str) -> str:
    return f"{organization_id}:{endpoint}:{idempotency_key}"


async def run_idempotent(
    db: AsyncSession,
    *,
    organization_id: uuid.UUID,
    endpoint: str,
    idempotency_key: str | None,
    fn: Callable[[], Awaitable[tuple[int, dict[str, Any]]]],
) -> tuple[int, dict[str, Any]]:
    """Run `fn()` at most once per (organization, endpoint, idempotency_key).

    A replayed request with the same key returns the original response
    without re-running `fn`. Requests without an Idempotency-Key header
    always run `fn` directly (no idempotency guarantee requested).
    """
    if not idempotency_key:
        return await fn()

    key = _storage_key(organization_id, endpoint, idempotency_key)

    existing = (
        await db.execute(select(IdempotencyKey).where(IdempotencyKey.key == key))
    ).scalar_one_or_none()
    if existing is not None:
        return existing.response_status, existing.response_body

    status_code, body = await fn()

    stmt = (
        pg_insert(IdempotencyKey)
        .values(
            key=key,
            organization_id=organization_id,
            endpoint=endpoint,
            response_status=status_code,
            response_body=body,
        )
        .on_conflict_do_nothing(index_elements=[IdempotencyKey.key])
    )
    await db.execute(stmt)
    await db.commit()

    return status_code, body
