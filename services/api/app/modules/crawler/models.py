"""§67 crawl_pages, §68 page_links."""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import ARRAY, BigInteger, Boolean, DateTime, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
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

    # M2 additions — extend the rule set toward 100+ (§144/M2) without
    # re-parsing HTML: heading structure, social/meta tags, hreflang,
    # image quality, security headers, and sitemap provenance.
    h2_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    h3_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    heading_order_valid: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    has_og_title: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    has_og_description: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    has_og_image: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    has_twitter_card: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    has_viewport_meta: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    has_charset_meta: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    has_favicon: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    html_lang: Mapped[str | None] = mapped_column(String(20))
    hreflang_tags: Mapped[list[dict]] = mapped_column(JSONB, nullable=False, default=list)
    images_missing_dimensions: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    images_generic_alt: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    has_insecure_form_action: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    word_frequency_top_ratio: Mapped[float] = mapped_column(Numeric(5, 4), nullable=False, default=0)
    from_sitemap: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    x_robots_tag: Mapped[str | None] = mapped_column(String(255))
    security_headers: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    # Full parsed JSON-LD blocks (capped at extraction time) — schema_types
    # above only carries the @type name; this backs field-level validation
    # (e.g. Organization missing "name") and GEO entity-clarity scoring.
    schema_blocks: Mapped[list[dict]] = mapped_column(JSONB, nullable=False, default=list)
    is_redirect_loop: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

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
