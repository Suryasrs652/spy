# M4 load test

A lightweight async load generator against the live local stack — no k6/locust
dependency, just `httpx` + `asyncio` (already used elsewhere in this codebase).

```bash
docker compose exec api python -m loadtest.run                    # all scenarios
docker compose exec api python -m loadtest.run --scenario reads --n 500
```

Scenarios: `signup`, `reads`, `ratelimit`, `audits` (see `run.py` docstrings
for what each measures). This is not a benchmark chasing a specific number on
unknown hardware — it's a regression gate: capture a baseline on a given
machine, then re-run after a change that touches a hot path (auth,
entitlements, the rate limiter, the crawler pipeline) and compare.

## What this run found (and fixed)

Running it once, as intended, surfaced three real bugs that inspection alone
hadn't caught:

1. **Argon2id hashing blocked the whole event loop.** `hash_password`/
   `verify_password` (`app/core/security.py`) called Argon2id synchronously
   inside async request handlers. Since uvicorn runs one process with one
   event loop, every concurrent signup or login fully serialized behind
   whichever hash was already running — 50 concurrent signups measured a
   p99 of ~3.8s purely from that queuing. Fixed by moving both calls onto
   `asyncio.to_thread`; the same 50-signup run now measures ~2.0s p99, and
   more importantly the event loop stays free to serve unrelated requests
   while a hash is computing.

2. **The default DB connection pool (15 total: pool_size=5 + max_overflow=10)
   was too small for realistic concurrency.** 300 concurrent authenticated
   reads queued behind it, measuring a p99 of ~3s for what should be a
   single indexed SELECT. Raised to a configurable `DB_POOL_SIZE`/
   `DB_MAX_OVERFLOW` (default 10+10=20 per process) in `app/core/config.py`
   / `app/db/session.py` — tune per deployment based on Postgres's own
   `max_connections` and how many processes (api/worker/beat) share it.

3. **Celery workers reusing a pooled asyncpg connection across separate
   `asyncio.run()` calls crashed with "attached to a different loop".**
   `app/workers/tasks/crawl.py` calls `asyncio.run(_run_audit_async(...))`
   once per task; each call gets a fresh event loop, but the module-level
   SQLAlchemy engine's connection pool was still handing back connections
   opened on a *previous*, now-closed loop. In an 8-concurrent-audit run,
   3 audits silently got stranded (never reached a terminal status) with
   this error in the worker log. This is exactly the same class of bug
   `tests/conftest.py` already works around for pytest's per-test event
   loops (`USE_NULL_POOL`) — it just hadn't been applied to the real worker
   process. Fixed in `app/db/session.py`: `RUN_MODE=worker`/`beat` now force
   `NullPool` unconditionally (a fresh physical connection per checkout,
   safe across any number of event loops); `RUN_MODE=api` keeps the pool,
   since uvicorn holds one event loop for the process's entire lifetime.
   Re-running the same 8-concurrent-audit scenario after the fix: 0 errors,
   all 8 completed within ~6.4s.

4. **The Redis-backed fixed-window rate limiter held up correctly under a
   real concurrent burst** — 20 simultaneous signups against a 5-per-60s
   limit produced exactly 5 successes and 15 `429`s, confirming Redis
   `INCR`'s atomicity prevents the race a naive read-then-write limiter
   would be vulnerable to. (A correctness check riding along on a load
   test, not a bug — noted here since it's the kind of thing this exercise
   is also supposed to confirm.)
