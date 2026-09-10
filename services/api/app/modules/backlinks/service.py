"""§144/M5 — recording and querying Spy's own crawl-derived backlink index.
See models.py for what this table is and, importantly, isn't.
"""
from __future__ import annotations

import uuid
from urllib.parse import urlsplit

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.backlinks.models import DiscoveredBacklink
from app.modules.crawler.models import CrawlPage, PageLink


def _hostname(url: str) -> str:
    return (urlsplit(url).hostname or "").lower()


async def record_discovered_backlinks(
    db: AsyncSession, *, audit_id: uuid.UUID | None, pages: list[CrawlPage], links: list[PageLink]
) -> int:
    """Upserts one row per (source_url, target_url) external link found in
    this crawl. Called once per audit, after the crawl but independent of
    that audit's own retention lifecycle (§109) — these rows outlive the
    audit that found them.
    """
    page_by_id = {p.id: p for p in pages}
    rows: dict[tuple[str, str], dict] = {}

    for link in links:
        if link.is_internal or not link.source_page_id:
            continue
        source_page = page_by_id.get(link.source_page_id)
        if source_page is None or not source_page.indexable:
            continue
        target_domain = _hostname(link.target_url)
        source_domain = _hostname(source_page.url)
        if not target_domain or not source_domain or target_domain == source_domain:
            continue
        # A page linking to the same external target twice (e.g. a nav
        # logo link and a footer link) is one backlink fact, not two.
        key = (source_page.url, link.target_url)
        rows[key] = {
            "id": uuid.uuid4(),
            "source_url": source_page.url,
            "source_domain": source_domain,
            "target_url": link.target_url,
            "target_domain": target_domain,
            "anchor_text": link.anchor_text,
            "nofollow": link.nofollow,
            "discovered_by_audit_id": audit_id,
        }

    if not rows:
        return 0

    stmt = pg_insert(DiscoveredBacklink).values(list(rows.values()))
    stmt = stmt.on_conflict_do_update(
        index_elements=["source_url", "target_url"],
        set_={
            "anchor_text": stmt.excluded.anchor_text,
            "nofollow": stmt.excluded.nofollow,
            "discovered_by_audit_id": stmt.excluded.discovered_by_audit_id,
            "updated_at": func.now(),
        },
    )
    await db.execute(stmt)
    await db.commit()
    return len(rows)


async def get_backlinks_for_domain(
    db: AsyncSession, *, domain: str, limit: int = 100, offset: int = 0
) -> list[DiscoveredBacklink]:
    result = await db.execute(
        select(DiscoveredBacklink)
        .where(DiscoveredBacklink.target_domain == domain.lower())
        .order_by(DiscoveredBacklink.updated_at.desc())
        .limit(limit)
        .offset(offset)
    )
    return list(result.scalars().all())


async def get_backlink_summary(db: AsyncSession, *, domain: str) -> dict:
    result = await db.execute(
        select(
            func.count(),
            func.count(func.distinct(DiscoveredBacklink.source_domain)),
            func.count().filter(DiscoveredBacklink.nofollow.is_(False)),
        ).where(DiscoveredBacklink.target_domain == domain.lower())
    )
    total_backlinks, referring_domains, followed_backlinks = result.one()
    return {
        "domain": domain.lower(),
        "total_backlinks": total_backlinks,
        "referring_domains": referring_domains,
        "followed_backlinks": followed_backlinks,
    }
