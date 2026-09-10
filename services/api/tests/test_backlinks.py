"""§144/M5 — Spy's own crawl-derived backlink index, against real Postgres."""
from __future__ import annotations

import uuid

import pytest

from app.modules.backlinks.service import (
    get_backlink_summary,
    get_backlinks_for_domain,
    record_discovered_backlinks,
)
from app.modules.crawler.models import CrawlPage, PageLink


def _page(url: str, *, indexable: bool = True) -> CrawlPage:
    return CrawlPage(
        id=uuid.uuid4(), audit_id=None, project_id=uuid.uuid4(),
        url=url, normalized_url=url, indexable=indexable,
    )


def _external_link(source: CrawlPage, target_url: str, *, anchor_text: str | None = None, nofollow: bool = False) -> PageLink:
    return PageLink(
        id=uuid.uuid4(), audit_id=source.audit_id, source_page_id=source.id,
        target_url=target_url, is_internal=False, anchor_text=anchor_text, nofollow=nofollow,
    )


@pytest.mark.asyncio
async def test_records_external_links_as_backlinks(db):
    source = _page("https://blogger.example/post-1")
    links = [_external_link(source, "https://target.example/landing", anchor_text="great tool")]

    count = await record_discovered_backlinks(db, audit_id=None, pages=[source], links=links)
    assert count == 1

    backlinks = await get_backlinks_for_domain(db, domain="target.example")
    assert len(backlinks) == 1
    assert backlinks[0].source_domain == "blogger.example"
    assert backlinks[0].anchor_text == "great tool"


@pytest.mark.asyncio
async def test_internal_links_are_never_recorded(db):
    source = _page("https://onesite.example/a")
    internal_link = PageLink(
        id=uuid.uuid4(), audit_id=source.audit_id, source_page_id=source.id,
        target_url="https://onesite.example/b", is_internal=True,
    )
    count = await record_discovered_backlinks(db, audit_id=None, pages=[source], links=[internal_link])
    assert count == 0


@pytest.mark.asyncio
async def test_noindex_pages_do_not_contribute_backlinks(db):
    source = _page("https://blocked.example/a", indexable=False)
    links = [_external_link(source, "https://target2.example/")]
    count = await record_discovered_backlinks(db, audit_id=None, pages=[source], links=links)
    assert count == 0


@pytest.mark.asyncio
async def test_resync_updates_rather_than_duplicates(db):
    domain = f"resync-target-{uuid.uuid4().hex[:8]}.example"
    source = _page(f"https://blogger-{uuid.uuid4().hex[:8]}.example/post")

    await record_discovered_backlinks(
        db, audit_id=None, pages=[source],
        links=[_external_link(source, f"https://{domain}/", anchor_text="old anchor")],
    )
    await record_discovered_backlinks(
        db, audit_id=None, pages=[source],
        links=[_external_link(source, f"https://{domain}/", anchor_text="new anchor")],
    )

    backlinks = await get_backlinks_for_domain(db, domain=domain)
    assert len(backlinks) == 1, "re-discovering the same link must update, not duplicate, the row"
    assert backlinks[0].anchor_text == "new anchor"


@pytest.mark.asyncio
async def test_backlink_summary_counts_referring_domains_and_nofollow(db):
    domain = f"summary-target-{uuid.uuid4().hex[:8]}.example"
    page_a = _page(f"https://referrer-a-{uuid.uuid4().hex[:8]}.example/")
    page_b = _page(f"https://referrer-b-{uuid.uuid4().hex[:8]}.example/")

    await record_discovered_backlinks(
        db, audit_id=None, pages=[page_a, page_b],
        links=[
            _external_link(page_a, f"https://{domain}/one"),
            _external_link(page_a, f"https://{domain}/two"),
            _external_link(page_b, f"https://{domain}/three", nofollow=True),
        ],
    )

    summary = await get_backlink_summary(db, domain=domain)
    assert summary["total_backlinks"] == 3
    assert summary["referring_domains"] == 2
    assert summary["followed_backlinks"] == 2


@pytest.mark.asyncio
async def test_self_links_to_own_domain_are_not_backlinks(db):
    source = _page("https://samesite.example/a")
    # An absolute link back to the same domain, wrongly marked is_internal=False
    # by some upstream quirk — must still not count as a backlink to itself.
    links = [_external_link(source, "https://samesite.example/b")]
    count = await record_discovered_backlinks(db, audit_id=None, pages=[source], links=links)
    assert count == 0
