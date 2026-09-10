"""§67 crawl_pages, §68 page_links."""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import ARRAY, BigInteger, Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, UUIDPKMixin, utcnow


class CrawlPage(UUIDPKMixin, Base):
    __tablename__ = "crawl_pages"

    audit_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("audits.id", ondelete="CASCADE"), nullable=False, index=True
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )

    url: Mapped[str] = mapped_column(Text, nullable=False)
    normalized_url: Mapped[str] = mapped_column(Text, nullable=False, index=True)

    status_code: Mapped[int | None] = mapped_column(Integer)
    content_type: Mapped[str | None] = mapped_column(String(120))

    title: Mapped[str | None] = mapped_column(Text)
    meta_description: Mapped[str | None] = mapped_column(Text)
    h1: Mapped[str | None] = mapped_column(Text)

    canonical_url: Mapped[str | None] = mapped_column(Text)
    robots_meta: Mapped[str | None] = mapped_column(String(255))

    word_count: Mapped[int | None] = mapped_column(Integer)

    content_hash: Mapped[str | None] = mapped_column(String(64))
    html_hash: Mapped[str | None] = mapped_column(String(64))

    crawl_depth: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    indexable: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    robots_allowed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    response_ms: Mapped[int | None] = mapped_column(Integer)
    html_size: Mapped[int | None] = mapped_column(BigInteger)

    # Denormalized signals the rule engine (app/modules/seo/rules.py) reads
    # directly rather than re-parsing HTML during analysis — kept small and
    # derived-only, per §3's real-data -> deterministic-analysis pipeline.
    redirect_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    h1_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    images_total: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    images_missing_alt: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    has_schema: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    schema_types: Mapped[list[str]] = mapped_column(ARRAY(String), nullable=False, default=list)
    schema_invalid: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    mixed_content: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class PageLink(UUIDPKMixin, Base):
    __tablename__ = "page_links"

    audit_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("audits.id", ondelete="CASCADE"), nullable=False, index=True
    )

    source_page_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("crawl_pages.id", ondelete="CASCADE"), nullable=False, index=True
    )
    target_url: Mapped[str] = mapped_column(Text, nullable=False)
    target_page_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("crawl_pages.id", ondelete="SET NULL"), nullable=True
    )

    anchor_text: Mapped[str | None] = mapped_column(Text)

    is_internal: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    nofollow: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    ugc: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    sponsored: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    status_code: Mapped[int | None] = mapped_column(Integer)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
