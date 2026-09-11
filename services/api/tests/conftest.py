"""Shared test fixtures.

These tests run against a real Postgres + Redis (the docker-compose
services), not mocks — the release-blocking tests in particular are
exactly the tests where a mocked DB would hide the bugs they exist to
catch. Run them with:

    docker compose exec api pytest -q

The suite provisions and migrates its own database (`spy_test` by
default, override with TEST_DATABASE_NAME) and drops it at the start of
every run, so it never touches the development database. That isolation
is load-bearing rather than tidiness: `_reset_between_tests` below
truncates tables between test functions, and pointed at the dev database
that silently deleted real projects and their audits.
"""
from __future__ import annotations

import os
from urllib.parse import urlsplit, urlunsplit

# Everything in this block must happen before the first `from app...`
# import anywhere in the test process, because app.db.session builds its
# engine at import time from get_settings(), which is lru_cache'd.

# pytest-asyncio gives each test a fresh, function-scoped event loop, and
# asyncpg connections are bound to the loop that opened them — SQLAlchemy's
# default pool would hand the next test a connection whose loop is already
# closed ("Future attached to a different loop"). NullPool opens a fresh
# connection per checkout instead. See app/core/config.py:use_null_pool.
os.environ.setdefault("USE_NULL_POOL", "true")

TEST_DATABASE_NAME = os.environ.get("TEST_DATABASE_NAME", "spy_test")


def _with_database(url: str, name: str) -> str:
    parts = urlsplit(url)
    return urlunsplit((parts.scheme, parts.netloc, f"/{name}", parts.query, parts.fragment))


def _redirect_to_test_database() -> tuple[str, str]:
    """Point both DB URLs at the test database, returning the *admin* URLs
    (pointed at the `postgres` maintenance database) needed to create and
    drop it.

    Refuses if the test database would be the application's own, because
    provisioning DROPs it — and TEST_DATABASE_NAME is an override a person
    can set. Comparing the name against the configured application
    database is the only check that actually protects anything; comparing
    it against itself after redirection always passes.
    """
    from app.core.config import get_settings

    settings = get_settings()
    async_url, sync_url = settings.database_url, settings.database_url_sync
    app_database = urlsplit(async_url).path.lstrip("/")

    if app_database == TEST_DATABASE_NAME:
        raise RuntimeError(
            f"Refusing to run: TEST_DATABASE_NAME is {TEST_DATABASE_NAME!r}, which is the "
            f"application's own database. Provisioning DROPs the test database and the suite "
            f"truncates tables between tests, so this would destroy real data."
        )

    os.environ["DATABASE_URL"] = _with_database(async_url, TEST_DATABASE_NAME)
    os.environ["DATABASE_URL_SYNC"] = _with_database(sync_url, TEST_DATABASE_NAME)
    get_settings.cache_clear()  # so every later reader sees the test URLs

    return _with_database(sync_url, "postgres"), _with_database(sync_url, TEST_DATABASE_NAME)


_ADMIN_URL, _TEST_SYNC_URL = _redirect_to_test_database()


def _provision_test_database() -> None:
    """Drop and recreate the test database, then migrate it.

    Recreating per run rather than reusing means a failed run can't leave
    state that makes the next one pass (or fail) for the wrong reason. The
    schema comes from `alembic upgrade head` rather than
    `Base.metadata.create_all` specifically because the migrations also
    seed rule_config and feature_flags, which the rule engine reads — a
    create_all schema would be structurally right and behaviourally empty.
    """
    from sqlalchemy import create_engine, text

    from alembic import command
    from alembic.config import Config

    admin = create_engine(_ADMIN_URL, isolation_level="AUTOCOMMIT", future=True)
    with admin.connect() as conn:
        # Terminate stragglers from a previous interrupted run, or DROP blocks.
        conn.execute(
            text(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                "WHERE datname = :name AND pid <> pg_backend_pid()"
            ),
            {"name": TEST_DATABASE_NAME},
        )
        conn.execute(text(f'DROP DATABASE IF EXISTS "{TEST_DATABASE_NAME}"'))
        conn.execute(text(f'CREATE DATABASE "{TEST_DATABASE_NAME}"'))
    admin.dispose()

    alembic_cfg = Config(os.path.join(os.path.dirname(os.path.dirname(__file__)), "alembic.ini"))
    alembic_cfg.set_main_option("script_location", os.path.join(os.path.dirname(os.path.dirname(__file__)), "alembic"))
    alembic_cfg.set_main_option("sqlalchemy.url", _TEST_SYNC_URL)
    command.upgrade(alembic_cfg, "head")


_provision_test_database()

# E402 throughout: these imports are deliberately below the block above.
# app.db.session builds its engine at import time, so the DB URLs have to
# be redirected — and the database provisioned — before anything under
# `app.` is imported. Moving them to the top silently reintroduces the bug
# this file exists to prevent.
import asyncio  # noqa: E402
import uuid  # noqa: E402
from collections.abc import AsyncGenerator  # noqa: E402

import pytest  # noqa: E402
import pytest_asyncio  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession  # noqa: E402

from app.db.session import AsyncSessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402

# Aborts the run rather than letting it delete a real database.
# `_reset_between_tests` truncates tables, so if the redirection above
# ever silently stops working, this is the difference between a failed
# import and a destroyed development database. Deliberately a module-level
# assertion and not a test function: pytest does not collect tests from
# conftest.py, and this has to fire before any fixture runs.
if engine.url.database != TEST_DATABASE_NAME:
    raise RuntimeError(
        f"Refusing to run: tests are pointed at database {engine.url.database!r}, "
        f"not {TEST_DATABASE_NAME!r}. The test suite truncates tables between tests, "
        f"so running against anything else would destroy real data."
    )


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

    # Every test now shares the one local workspace instead of getting a
    # freshly-signed-up org, so project uniqueness — (organization_id,
    # canonical_origin), §63 — would collide across tests that audit the
    # same real domain. Clearing projects between tests restores the
    # isolation the per-test org used to provide; audits, crawl pages,
    # issues and reports all cascade from the project row.
    # Every test shares the one local workspace, so rows have to be
    # cleared between them: project uniqueness is (organization_id,
    # canonical_origin) (§63), and two tests auditing the same domain
    # would collide. Notifications are user-scoped rather than
    # project-scoped, so they don't cascade with the projects and need
    # clearing separately or they leak into the next test's unread counts.
    #
    # Safe only because this is a dedicated test database — see the
    # provisioning block and test_database_guard at the top of this file.
    from sqlalchemy import delete

    from app.db.session import AsyncSessionLocal
    from app.modules.notifications.models import Notification
    from app.modules.projects.models import Project

    async with AsyncSessionLocal() as session:
        await session.execute(delete(Notification))
        await session.execute(delete(Project))
        await session.commit()

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
    """Returns (user, organization_id, token) for the single local
    workspace.

    Spy is self-hosted and single-user now (app.core.local_workspace), so
    there is no signup and no token — but the tuple shape and the
    `auth_headers` fixture below are kept exactly as they were so every
    existing test's call sites stay unchanged.
    """
    from app.core.local_workspace import LOCAL_ORG_ID, get_local_user

    user = await get_local_user(db)
    return user, LOCAL_ORG_ID, ""


@pytest.fixture
def auth_headers():
    """No-op: requests carry no credentials now. Kept so tests can go on
    calling `auth_headers(token, org_id)` unchanged."""

    def _make(token: str = "", org_id=None) -> dict:
        return {}

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

    from app.workers.tasks import crawl as crawl_task_module

    def _fake_delay(audit_id: str) -> None:
        asyncio.ensure_future(crawl_task_module._run_audit_async(audit_id))

    monkeypatch.setattr(crawl_task_module.run_audit_task, "delay", _fake_delay)
    yield


async def wait_for_audit_terminal(db: AsyncSession, audit_id, *, timeout: float = 30.0):
    """Poll the DB until the audit reaches a terminal status — the test
    equivalent of a client polling `GET /audits/{id}/progress`.
    """

    from sqlalchemy import select

    from app.modules.audits.models import TERMINAL_STATUSES, Audit

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
