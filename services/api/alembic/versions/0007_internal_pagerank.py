"""M5: internal PageRank column on crawl_pages (§144)

Revision ID: 0007
Revises: 0006
Create Date: 2026-09-10
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0007"
down_revision: Union[str, None] = "0006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("crawl_pages", sa.Column("internal_pagerank", sa.Numeric(6, 2), nullable=True))


def downgrade() -> None:
    op.drop_column("crawl_pages", "internal_pagerank")
