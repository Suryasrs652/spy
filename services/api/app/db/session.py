"""Async SQLAlchemy engine/session factory."""
from __future__ import annotations

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import get_settings

settings = get_settings()

# §104 load-test finding: app/workers/tasks/crawl.py's Celery tasks call
# `asyncio.run(...)` once per task, each creating and then closing its own
# event loop. A pooled connection is only ever safe to hand back out on the
# loop that opened it, so the moment one worker process handles a second
# task and the pool reuses a connection from the first task's now-dead
# loop, asyncpg raises "attached to a different loop" — this reproduced
# reliably as several audits in a concurrent batch getting silently
# stranded (never reaching a terminal status). The `api` process has no
# such problem: uvicorn keeps one event loop alive for the process's whole
# lifetime, so its connections are always reused on the loop that made
# them.
_needs_null_pool = settings.use_null_pool or settings.run_mode in ("worker", "beat")

_engine_kwargs = {
    "pool_pre_ping": True,
    "future": True,
    "pool_size": settings.db_pool_size,
    "max_overflow": settings.db_max_overflow,
    "pool_timeout": settings.db_pool_timeout_seconds,
}
if _needs_null_pool:
    _engine_kwargs = {"poolclass": NullPool, "future": True}

engine = create_async_engine(settings.database_url, **_engine_kwargs)

AsyncSessionLocal = async_sessionmaker(
    bind=engine, expire_on_commit=False, autoflush=False, class_=AsyncSession
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        yield session
