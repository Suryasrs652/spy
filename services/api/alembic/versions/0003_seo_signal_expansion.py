"""M2: crawl_pages signal expansion for the 100+ rule set (§144/M2)

Revision ID: 0003
Revises: 0002
Create Date: 2026-09-10
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql as pg

revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("crawl_pages", sa.Column("h2_count", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("crawl_pages", sa.Column("h3_count", sa.Integer(), nullable=False, server_default="0"))
    op.add_column(
        "crawl_pages", sa.Column("heading_order_valid", sa.Boolean(), nullable=False, server_default=sa.true())
    )
    op.add_column(
        "crawl_pages", sa.Column("has_og_title", sa.Boolean(), nullable=False, server_default=sa.false())
    )
    op.add_column(
        "crawl_pages", sa.Column("has_og_description", sa.Boolean(), nullable=False, server_default=sa.false())
    )
    op.add_column(
        "crawl_pages", sa.Column("has_og_image", sa.Boolean(), nullable=False, server_default=sa.false())
    )
    op.add_column(
        "crawl_pages", sa.Column("has_twitter_card", sa.Boolean(), nullable=False, server_default=sa.false())
    )
    op.add_column(
        "crawl_pages", sa.Column("has_viewport_meta", sa.Boolean(), nullable=False, server_default=sa.false())
    )
    op.add_column(
        "crawl_pages", sa.Column("has_charset_meta", sa.Boolean(), nullable=False, server_default=sa.false())
    )
    op.add_column(
        "crawl_pages", sa.Column("has_favicon", sa.Boolean(), nullable=False, server_default=sa.false())
    )
    op.add_column("crawl_pages", sa.Column("html_lang", sa.String(20), nullable=True))
    op.add_column(
        "crawl_pages", sa.Column("hreflang_tags", pg.JSONB(), nullable=False, server_default="[]")
    )
    op.add_column(
        "crawl_pages", sa.Column("images_missing_dimensions", sa.Integer(), nullable=False, server_default="0")
    )
    op.add_column(
        "crawl_pages", sa.Column("images_generic_alt", sa.Integer(), nullable=False, server_default="0")
    )
    op.add_column(
        "crawl_pages",
        sa.Column("has_insecure_form_action", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column(
        "crawl_pages", sa.Column("word_frequency_top_ratio", sa.Numeric(5, 4), nullable=False, server_default="0")
    )
    op.add_column(
        "crawl_pages", sa.Column("from_sitemap", sa.Boolean(), nullable=False, server_default=sa.false())
    )
    op.add_column("crawl_pages", sa.Column("x_robots_tag", sa.String(255), nullable=True))
    op.add_column(
        "crawl_pages", sa.Column("security_headers", pg.JSONB(), nullable=False, server_default="{}")
    )


def downgrade() -> None:
    for col in [
        "security_headers", "x_robots_tag", "from_sitemap", "word_frequency_top_ratio",
        "has_insecure_form_action", "images_generic_alt", "images_missing_dimensions",
        "hreflang_tags", "html_lang", "has_favicon", "has_charset_meta", "has_viewport_meta",
        "has_twitter_card", "has_og_image", "has_og_description", "has_og_title",
        "heading_order_valid", "h3_count", "h2_count",
    ]:
        op.drop_column("crawl_pages", col)
