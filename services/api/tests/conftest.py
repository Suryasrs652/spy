"""Shared test fixtures.

These tests run against a real Postgres + Redis (the docker-compose
services), not mocks — the release-blocking tests in particular (§118-§123)
are exactly the tests where a mocked DB would hide the bugs they exist to
catch (the partial-unique-index race, the webhook-uniqueness race). Run them
with:

    docker compose exec api pytest -q

Known limitation: this does not yet provision an isolated `spy_test`
database — tests run against whatever DATABASE_URL is configured and rely
on randomized unique identifiers (email/domain per test) rather than a
pristine schema per run. Isolating onto a dedicated test database is
tracked as a follow-up, not implemented here.
"""
from __future__ import annotations

import os

# Must be set before the first `from app...` import anywhere in the test
# process: app.db.session builds its engine at import time from
# get_settings() (lru_cache'd), and pytest-asyncio's function-scoped event
# loops mean SQLAlchemy's default pool would otherwise hold asyncpg
# connections bound to a loop that's already been torn down by the time the
# next test runs ("Future attached to a different loop"). NullPool opens a
# fresh connection per checkout instead of reusing one across loops. See
# app/core/config.py:use_null_pool and app/db/session.py.
os.environ.setdefault("USE_NULL_POOL", "true")

import asyncio
import uuid
from collections.abc import AsyncGenerator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import AsyncSessionLocal
from app.main import app


@pytest_asyncio.fixture(autouse=True)
async def _reset_between_tests() -> AsyncGenerator[None, None]:
    """Flushes Redis before each test: the rate limiter (app.core.ratelimit)
    keys its buckets by client IP, and httpx's ASGITransport gives every
    test the same synthetic client address — without a flush, a rate-limit
    budget consumed by one test (e.g. 20 audit-creation attempts in the
    concurrency test) would carry over into the next test in the same
    60-second window and produce unrelated 429s.

    (The engine itself uses NullPool under USE_NULL_POOL=true — set above,
    before any `app.*` import — specifically so no pooled connection is
    ever reused across the function-scoped event loop pytest-asyncio gives
    each test; see app/db/session.py.)
    """
    from app.db.redis import get_redis

    # Same cross-loop staleness class of bug as the DB engine (see
    # USE_NULL_POOL above), but for the @lru_cache'd redis.asyncio client:
    # clear the cache so this test gets a fresh client — and thus a fresh
    # connection pool — bound to *its* event loop, not a previous test's
    # already-closed one.
    try:
        await get_redis().aclose()
    except Exception:  # noqa: BLE001 - previous client's loop may already be gone
        pass
    get_redis.cache_clear()

    await get_redis().flushdb()
    yield


def unique_email() -> str:
    # Not .test/.example — email-validator (a real dependency, not mocked)
    # rejects RFC 2606 reserved TLDs outright as "special-use" domains.
    # example.com itself is fine: only reserved for documentation, not
    # syntactically special-cased by the validator.
    return f"test-{uuid.uuid4().hex[:12]}@example.com"


def unique_domain() -> str:
    # Must be a domain that actually resolves — project creation runs
    # through the real SSRF guard (app.core.net.safe_client), which does a
    # genuine DNS lookup, not a mock. A non-resolving *.example.test host
    # would fail as DNS_FAILURE before the test even gets to what it's
    # testing. Project uniqueness is scoped to (organization_id,
    # canonical_origin) (§63), and every test gets a fresh org, so reusing
    # the same real origin across tests never collides.
    return "https://example.com"


@pytest_asyncio.fixture
async def db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        yield session


@pytest_asyncio.fixture
async def client() -> AsyncGenerator[AsyncClient, None]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
        yield ac


@pytest_asyncio.fixture
async def verified_user(db: AsyncSession):
    """Creates a fresh, already-email-verified user + workspace, and
    returns (user, organization_id, access_token) — bypassing the
    email-verification-link round trip since these tests aren't about the
    email flow itself.
    """
    from app.core.security import issue_access_token
    from app.modules.auth import service as auth_service
    from datetime import datetime, timezone

    email = unique_email()
    user, org_id = await auth_service.signup(db, email=email, password="correct horse battery staple", name=None)
    user.email_verified_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(user)

    token = issue_access_token(str(user.id), str(org_id))
    return user, org_id, token


@pytest.fixture
def auth_headers():
    def _make(token: str, org_id) -> dict:
        return {"Authorization": f"Bearer {token}", "X-Organization-Id": str(org_id)}

    return _make


@pytest.fixture(autouse=True)
def inline_audit_task(monkeypatch):
    """Runs the audit pipeline on the test's own running event loop instead
    of publishing to a real Celery broker — `.delay()` is fire-and-forget in
    both cases (matching production's "enqueue after commit, never block the
    request" contract, §157), so tests poll for completion via
    `wait_for_audit_terminal` below, exactly as a real client would poll
    `GET /audits/{id}/progress`.
    """
    import asyncio

    from app.workers.tasks import crawl as crawl_task_module

    def _fake_delay(audit_id: str) -> None:
        asyncio.ensure_future(crawl_task_module._run_audit_async(audit_id))

    monkeypatch.setattr(crawl_task_module.run_audit_task, "delay", _fake_delay)
    yield


async def wait_for_audit_terminal(db: AsyncSession, audit_id, *, timeout: float = 30.0):
    """Poll the DB until the audit reaches a terminal status — the test
    equivalent of a client polling `GET /audits/{id}/progress`.
    """
    import asyncio

    from app.modules.audits.models import Audit, TERMINAL_STATUSES
    from sqlalchemy import select

    terminal = {s.value for s in TERMINAL_STATUSES}
    elapsed = 0.0
    interval = 0.1
    while elapsed < timeout:
        db.expire_all()
        audit = (await db.execute(select(Audit).where(Audit.id == audit_id))).scalar_one()
        if audit.status in terminal:
            return audit
        await asyncio.sleep(interval)
        elapsed += interval
    raise TimeoutError(f"Audit {audit_id} did not reach a terminal status within {timeout}s")
