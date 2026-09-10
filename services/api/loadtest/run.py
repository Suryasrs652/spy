"""§104/M4 load test — a lightweight async load generator against the live
local stack. No k6/locust dependency: httpx + asyncio, both already used
elsewhere in this codebase.

Run inside the api container so it can hit the API over real HTTP (real
ASGI stack, real Redis-backed rate limiter, real Postgres) while also
reaching Postgres directly to seed verified users without the email round
trip:

    docker compose exec api python loadtest/run.py
    docker compose exec api python loadtest/run.py --scenario reads --n 500

This is not a benchmark chasing a specific number on unknown hardware — it
is a regression gate: capture a baseline on this machine, then re-run after
a change that touches a hot path (auth, entitlements, the rate limiter) and
compare. The `concurrent_audits` scenario in particular re-exercises the
entitlement race-prevention under real concurrent multi-user load, a
stronger version of the single-user 20-concurrent-request test in
test_release_blocking.py.
"""
from __future__ import annotations

import argparse
import asyncio
import time
import uuid
from dataclasses import dataclass, field

import httpx

BASE_URL = "http://localhost:8000/api/v1"


@dataclass
class ScenarioResult:
    name: str
    latencies_ms: list[float] = field(default_factory=list)
    statuses: dict[int, int] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)

    def record(self, elapsed_ms: float, status: int | None, error: str | None = None) -> None:
        self.latencies_ms.append(elapsed_ms)
        if status is not None:
            self.statuses[status] = self.statuses.get(status, 0) + 1
        if error:
            self.errors.append(error)

    def report(self) -> str:
        lat = sorted(self.latencies_ms)
        n = len(lat)

        def pct(p: float) -> float:
            if not lat:
                return 0.0
            idx = min(n - 1, int(n * p))
            return lat[idx]

        lines = [
            f"\n=== {self.name} ===",
            f"requests: {n}   errors: {len(self.errors)}",
            f"status codes: {dict(sorted(self.statuses.items()))}",
            f"latency ms — p50: {pct(0.50):.1f}  p95: {pct(0.95):.1f}  p99: {pct(0.99):.1f}  max: {max(lat, default=0):.1f}",
        ]
        if self.errors:
            lines.append(f"first error: {self.errors[0]}")
        return "\n".join(lines)


def _unique_email() -> str:
    return f"loadtest-{uuid.uuid4().hex[:16]}@example.com"


async def _timed(result: ScenarioResult, coro) -> None:
    start = time.perf_counter()
    try:
        status = await coro
        result.record((time.perf_counter() - start) * 1000, status)
    except Exception as exc:  # noqa: BLE001 - a failed request is a data point, not a crash
        result.record((time.perf_counter() - start) * 1000, None, str(exc))


async def scenario_signup_throughput(n: int) -> ScenarioResult:
    """Argon2id hashing is deliberately slow (§105) — this measures how
    that CPU cost holds up under concurrent signups. Calls the service
    function directly rather than POST /auth/signup: that endpoint is
    rate-limited to 5/60s per IP (correctly — see the `ratelimit`
    scenario), which would dominate this measurement and hide the number
    this scenario actually wants: how much signup throughput the
    hashing+DB layer itself can sustain, i.e. real deployment capacity
    planning, not the deliberate per-IP throttle.
    """
    from app.db.session import AsyncSessionLocal
    from app.modules.auth import service as auth_service

    result = ScenarioResult("signup_throughput (direct, bypasses the per-IP rate limit — see `ratelimit` scenario for that)")

    async def one():
        async with AsyncSessionLocal() as db:
            await auth_service.signup(db, email=_unique_email(), password="correct horse battery staple", name=None)
        return 201

    await asyncio.gather(*[_timed(result, one()) for _ in range(n)])
    return result


async def _seed_verified_users(db, n: int) -> list[tuple[str, str]]:
    """Returns (org_id, access_token) pairs, bypassing the email-verify
    round trip the same way tests/conftest.py's `verified_user` fixture
    does — this scenario is about read-path throughput, not signup.
    """
    from datetime import datetime, timezone

    from app.core.security import issue_access_token
    from app.modules.auth import service as auth_service

    users = []
    for _ in range(n):
        user, org_id = await auth_service.signup(
            db, email=_unique_email(), password="correct horse battery staple", name=None
        )
        user.email_verified_at = datetime.now(timezone.utc)
        users.append((str(org_id), issue_access_token(str(user.id), str(org_id))))
    await db.commit()
    return users


async def scenario_authenticated_reads(n: int) -> ScenarioResult:
    from app.db.session import AsyncSessionLocal

    result = ScenarioResult("authenticated_reads")
    pool_size = max(10, n // 10)

    async with AsyncSessionLocal() as db:
        users = await _seed_verified_users(db, pool_size)

    async with httpx.AsyncClient(base_url=BASE_URL, timeout=30.0, limits=httpx.Limits(max_connections=1000, max_keepalive_connections=200)) as client:

        async def one(org_id: str, token: str, path: str):
            resp = await client.get(
                path, headers={"Authorization": f"Bearer {token}", "X-Organization-Id": org_id}
            )
            return resp.status_code

        tasks = []
        for i in range(n):
            org_id, token = users[i % pool_size]
            path = "/entitlements/audit" if i % 2 == 0 else "/projects"
            tasks.append(_timed(result, one(org_id, token, path)))
        await asyncio.gather(*tasks)
    return result


async def scenario_rate_limiter_correctness(concurrency: int) -> ScenarioResult:
    """Fires far more concurrent requests than the signup rate limit
    (5/60s, app/modules/auth/router.py) allows, all in one burst. Redis
    INCR is atomic, so exactly `limit` should succeed regardless of how
    many requests race — this is a correctness check disguised as a load
    test, not just a throughput number.
    """
    result = ScenarioResult(f"rate_limiter_correctness (burst={concurrency}, limit=5/60s)")

    async with httpx.AsyncClient(base_url=BASE_URL, timeout=30.0, limits=httpx.Limits(max_connections=1000, max_keepalive_connections=200)) as client:

        async def one():
            resp = await client.post(
                "/auth/signup",
                json={"email": _unique_email(), "password": "correct horse battery staple"},
            )
            return resp.status_code

        await asyncio.gather(*[_timed(result, one()) for _ in range(concurrency)])

    allowed = result.statuses.get(201, 0)
    limited = result.statuses.get(429, 0)
    print(f"  -> {allowed} succeeded, {limited} rate-limited (all from one IP, sharing one 60s window bucket)")
    return result


async def scenario_concurrent_audits(n: int) -> ScenarioResult:
    """N different users, each running their free audit against the same
    small real site at once — exercises the crawler's per-host/global
    concurrency limits, the real Celery worker's queue throughput, and the
    entitlement system under real multi-user concurrency (not just one
    user racing itself, which test_release_blocking.py's concurrency test
    already covers). Requires the `worker` container to actually be
    running (docker compose up -d), since audit creation only enqueues the
    job — this scenario polls for real completion via the same endpoint a
    browser would.
    """
    from app.db.session import AsyncSessionLocal

    result = ScenarioResult(f"concurrent_audits (n={n}, target=https://example.com)")

    async with AsyncSessionLocal() as db:
        users = await _seed_verified_users(db, n)

    async with httpx.AsyncClient(base_url=BASE_URL, timeout=60.0, limits=httpx.Limits(max_connections=1000, max_keepalive_connections=200)) as client:
        audit_ids = []
        for org_id, token in users:
            headers = {"Authorization": f"Bearer {token}", "X-Organization-Id": org_id}
            start = time.perf_counter()
            proj_resp = await client.post(
                "/projects", json={"name": "Load Test Site", "url": "https://example.com"}, headers=headers
            )
            if proj_resp.status_code != 201:
                result.record((time.perf_counter() - start) * 1000, proj_resp.status_code, proj_resp.text[:200])
                continue
            project_id = proj_resp.json()["id"]

            audit_resp = await client.post("/audits", json={"project_id": project_id}, headers=headers)
            result.record((time.perf_counter() - start) * 1000, audit_resp.status_code)
            if audit_resp.status_code == 201:
                audit_ids.append((audit_resp.json()["id"], headers))

        completion = ScenarioResult(f"concurrent_audits — time to COMPLETED (n={len(audit_ids)})")

        async def wait_for_completion(audit_id: str, headers: dict) -> None:
            start = time.perf_counter()
            deadline = start + 90
            while time.perf_counter() < deadline:
                resp = await client.get(f"/audits/{audit_id}/progress", headers=headers)
                if resp.status_code == 200 and resp.json()["status"] in ("COMPLETED", "FAILED", "CANCELLED"):
                    completion.record((time.perf_counter() - start) * 1000, resp.json()["status"] == "COMPLETED" and 200 or 500)
                    return
                await asyncio.sleep(1)
            result.errors.append(f"audit {audit_id} did not reach a terminal status within 90s")

        await asyncio.gather(*[wait_for_completion(aid, h) for aid, h in audit_ids])
        print(completion.report())

    return result


SCENARIOS = {
    "signup": lambda args: scenario_signup_throughput(args.n),
    "reads": lambda args: scenario_authenticated_reads(args.n),
    "ratelimit": lambda args: scenario_rate_limiter_correctness(args.n),
    "audits": lambda args: scenario_concurrent_audits(args.n),
}


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scenario", choices=[*SCENARIOS, "all"], default="all")
    parser.add_argument("--n", type=int, default=None, help="Request/user count (scenario-specific default otherwise)")
    args = parser.parse_args()

    defaults = {"signup": 50, "reads": 300, "ratelimit": 20, "audits": 8}
    to_run = list(SCENARIOS) if args.scenario == "all" else [args.scenario]

    for name in to_run:
        n = args.n if args.n is not None else defaults[name]
        args.n = n
        print(f"\nRunning {name!r} (n={n})...")
        result = await SCENARIOS[name](args)
        print(result.report())
        args.n = None  # reset so the next scenario picks its own default


if __name__ == "__main__":
    asyncio.run(main())
