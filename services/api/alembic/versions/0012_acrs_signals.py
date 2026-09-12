"""Add the per-page inputs for AI Citation Readiness (ACRS).

Four structural signals the crawler can observe: how many checkable figures
a page states, whether it carries a date, and how much of its prose survives
being lifted out of context. See app/modules/scoring/acrs.py.

Revision ID: 0012
Revises: 0011
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0012"
down_revision: str | None = "0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("crawl_pages", sa.Column("statistic_count", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("crawl_pages", sa.Column("has_publication_date", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("crawl_pages", sa.Column("paragraph_count", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("crawl_pages", sa.Column("self_contained_paragraph_count", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("audits", sa.Column("acrs_score", sa.Numeric(5, 2), nullable=True))


def downgrade() -> None:
    op.drop_column("audits", "acrs_score")
    op.drop_column("crawl_pages", "self_contained_paragraph_count")
    op.drop_column("crawl_pages", "paragraph_count")
    op.drop_column("crawl_pages", "has_publication_date")
    op.drop_column("crawl_pages", "statistic_count")
