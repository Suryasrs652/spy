"""Release-blocking tests.

Originally §118-§123, which were mostly about the commercial core: the
free-audit entitlement race, payment failure, webhook idempotency and
cross-tenant isolation. Spy is now a self-hosted, single-user, free tool
— there is no billing, no entitlement and no second tenant to isolate
from — so those tests are gone with the code they covered.

What survives is what still has teeth on a tool anyone can point at an
arbitrary URL: the SSRF guard (§123), and the guarantee that a failed
audit leaves the system in a state the user can retry from (§119).
"""
from __future__ import annotations

import uuid

import pytest

from tests.conftest import unique_domain, wait_for_audit_terminal


# ── §119: a worker crash leaves a clean, retryable failure ──────────────
@pytest.mark.asyncio
async def test_audit_worker_error_fails_cleanly_and_can_be_retried(
    client, db, auth_headers, verified_user, monkeypatch
):
    from app.modules.audits.models import AuditStatus

    user, org_id, token = verified_user
    headers = auth_headers(token, org_id)

    project_resp = await client.post(
        "/api/v1/projects", json={"name": "Will Fail", "url": "https://example.com"}, headers=headers
    )
    project_id = project_resp.json()["id"]

    async def _boom(*args, **kwargs):
        raise RuntimeError("simulated worker crash")

    monkeypatch.setattr("app.workers.tasks.crawl.crawl_site", _boom)

    audit_resp = await client.post("/api/v1/audits", json={"project_id": project_id}, headers=headers)
    audit_id = uuid.UUID(audit_resp.json()["id"])

    audit = await wait_for_audit_terminal(db, audit_id, timeout=30)
    assert audit.status == AuditStatus.FAILED.value
    assert audit.failure_code == "WORKER_ERROR"

    # Nothing was consumed and nothing is locked: a retry is just allowed.
    retry_resp = await client.post("/api/v1/audits", json={"project_id": project_id}, headers=headers)
    assert retry_resp.status_code == 201


# ── §123: SSRF guard, end to end through the API ────────────────────────
@pytest.mark.asyncio
@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1/",
        "http://169.254.169.254/latest/meta-data/",
        "http://10.0.0.5/",
        "http://192.168.1.1/",
        "http://localhost/",
    ],
)
async def test_project_creation_blocks_ssrf_targets(client, auth_headers, verified_user, url):
    user, org_id, token = verified_user
    headers = auth_headers(token, org_id)
    resp = await client.post("/api/v1/projects", json={"name": "Evil", "url": url}, headers=headers)
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "BLOCKED_TARGET"


# ── Unmetered means unmetered: concurrent runs all succeed ──────────────
@pytest.mark.asyncio
async def test_concurrent_audit_requests_all_succeed(client, db, auth_headers, verified_user):
    """The inverse of the old free-audit race test: with nothing metered,
    five simultaneous requests must produce five audits, not one."""
    import asyncio

    from sqlalchemy import func, select

    from app.modules.audits.models import Audit

    user, org_id, token = verified_user
    headers = auth_headers(token, org_id)

    project_resp = await client.post(
        "/api/v1/projects", json={"name": "Race", "url": unique_domain()}, headers=headers
    )
    project_id = project_resp.json()["id"]

    async def _attempt():
        return await client.post("/api/v1/audits", json={"project_id": project_id}, headers=headers)

    results = await asyncio.gather(*[_attempt() for _ in range(5)])
    assert [r.status_code for r in results] == [201] * 5

    count = (
        await db.execute(
            select(func.count()).select_from(Audit).where(Audit.project_id == uuid.UUID(project_id))
        )
    ).scalar_one()
    assert count == 5
