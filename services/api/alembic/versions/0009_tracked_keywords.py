"""M5: rank tracking - tracked_keywords table (§144)

Revision ID: 0009
Revises: 0008
Create Date: 2026-09-10
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql as pg

revision: str = "0009"
down_revision: Union[str, None] = "0008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "tracked_keywords",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "organization_id", pg.UUID(as_uuid=True),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column(
            "project_id", pg.UUID(as_uuid=True),
            sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column("keyword", sa.Text(), nullable=False),
        sa.Column("added_by", pg.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("project_id", "keyword", name="uq_tracked_keyword_project"),
    )
    op.create_index("ix_tracked_keywords_organization_id", "tracked_keywords", ["organization_id"])
    op.create_index("ix_tracked_keywords_project_id", "tracked_keywords", ["project_id"])


def downgrade() -> None:
    op.drop_index("ix_tracked_keywords_project_id", table_name="tracked_keywords")
    op.drop_index("ix_tracked_keywords_organization_id", table_name="tracked_keywords")
    op.drop_table("tracked_keywords")
