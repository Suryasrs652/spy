"""M5: competitor benchmarking (§144)

Revision ID: 0010
Revises: 0009
Create Date: 2026-09-10
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql as pg

revision: str = "0010"
down_revision: Union[str, None] = "0009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "competitors",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "organization_id", pg.UUID(as_uuid=True),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column(
            "project_id", pg.UUID(as_uuid=True),
            sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column("added_by", pg.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("domain", sa.String(255), nullable=False),
        sa.Column("canonical_origin", sa.Text(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="PENDING"),
        sa.Column("last_crawled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("failure_message", sa.Text(), nullable=True),
        sa.Column("spy_score", sa.Numeric(5, 2), nullable=True),
        sa.Column("technical_score", sa.Numeric(5, 2), nullable=True),
        sa.Column("seo_score", sa.Numeric(5, 2), nullable=True),
        sa.Column("content_score", sa.Numeric(5, 2), nullable=True),
        sa.Column("performance_score", sa.Numeric(5, 2), nullable=True),
        sa.Column("aeo_score", sa.Numeric(5, 2), nullable=True),
        sa.Column("geo_score", sa.Numeric(5, 2), nullable=True),
        sa.Column("evidence", pg.JSONB(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("project_id", "canonical_origin", name="uq_competitor_project_origin"),
    )
    op.create_index("ix_competitors_organization_id", "competitors", ["organization_id"])
    op.create_index("ix_competitors_project_id", "competitors", ["project_id"])


def downgrade() -> None:
    op.drop_index("ix_competitors_project_id", table_name="competitors")
    op.drop_index("ix_competitors_organization_id", table_name="competitors")
    op.drop_table("competitors")
