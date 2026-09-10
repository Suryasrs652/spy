"""§144/M5 — Spy's own crawl-derived backlink index.

Not a third-party backlink database: every row here is a real external
link Spy's own crawler actually found while auditing *some* site (not
necessarily the one it points at). There is no free, live-queryable "who
links to domain X" API — Common Crawl's CDX index only looks up a URL's
own crawl history, not its inbound link graph, and a real backlink index
(Ahrefs/Majestic-class) means running your own web-scale crawler, which is
exactly what building this table out of Spy's audit crawls does, just
starting from zero coverage instead of years of it. Coverage is therefore
bounded by what Spy has already crawled — real data, not manufactured
(§3), but not comprehensive, and every consumer of this table must not
present it as if it were.

Durable and independent of any one audit's lifecycle — unlike `PageLink`
(scoped to one audit and purged by the §109 retention job), a discovered
backlink stays valid until it's re-confirmed absent, so it lives in its
own table that only grows.
"""
from __future__ import annotations

import uuid

from sqlalchemy import Boolean, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPKMixin


class DiscoveredBacklink(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "discovered_backlinks"
    __table_args__ = (UniqueConstraint("source_url", "target_url", name="uq_backlink_source_target"),)

    source_url: Mapped[str] = mapped_column(Text, nullable=False)
    source_domain: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    target_url: Mapped[str] = mapped_column(Text, nullable=False)
    target_domain: Mapped[str] = mapped_column(String(255), nullable=False, index=True)

    anchor_text: Mapped[str | None] = mapped_column(Text)
    nofollow: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # The audit that most recently confirmed this link exists — nullable
    # because the audit itself can later be deleted/purged while the
    # backlink fact it discovered remains valid.
    discovered_by_audit_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("audits.id", ondelete="SET NULL"), nullable=True
    )

    # created_at (TimestampMixin) = first_seen; updated_at = last confirmed
    # present. Neither column is touched if a later crawl finds the exact
    # same (source_url, target_url) pair again except via the upsert's
    # ON CONFLICT DO UPDATE, which bumps updated_at — see sync in service.py.
