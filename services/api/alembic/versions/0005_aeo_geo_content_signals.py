"""M2: full §48/§49 AEO/GEO scoring — question-heading coverage, structured
content (lists/tables/definitions), and author byline attribution.

Revision ID: 0005
Revises: 0004
Create Date: 2026-09-10
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: Union[str, None] = "0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("crawl_pages", sa.Column("question_heading_count", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("crawl_pages", sa.Column("list_count", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("crawl_pages", sa.Column("table_count", sa.Integer(), nullable=False, server_default="0"))
    op.add_column(
        "crawl_pages", sa.Column("has_definition_list", sa.Boolean(), nullable=False, server_default=sa.false())
    )
    op.add_column(
        "crawl_pages", sa.Column("has_author_byline", sa.Boolean(), nullable=False, server_default=sa.false())
    )


def downgrade() -> None:
    op.drop_column("crawl_pages", "has_author_byline")
    op.drop_column("crawl_pages", "has_definition_list")
    op.drop_column("crawl_pages", "table_count")
    op.drop_column("crawl_pages", "list_count")
    op.drop_column("crawl_pages", "question_heading_count")
