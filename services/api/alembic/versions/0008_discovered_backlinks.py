"""M5: Spy's own crawl-derived backlink index (§144)

Revision ID: 0008
Revises: 0007
Create Date: 2026-09-10
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql as pg

revision: str = "0008"
down_revision: Union[str, None] = "0007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "discovered_backlinks",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("source_url", sa.Text(), nullable=False),
        sa.Column("source_domain", sa.String(255), nullable=False),
        sa.Column("target_url", sa.Text(), nullable=False),
        sa.Column("target_domain", sa.String(255), nullable=False),
        sa.Column("anchor_text", sa.Text(), nullable=True),
        sa.Column("nofollow", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column(
            "discovered_by_audit_id", pg.UUID(as_uuid=True),
            sa.ForeignKey("audits.id", ondelete="SET NULL"), nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("source_url", "target_url", name="uq_backlink_source_target"),
    )
    op.create_index("ix_discovered_backlinks_source_domain", "discovered_backlinks", ["source_domain"])
    op.create_index("ix_discovered_backlinks_target_domain", "discovered_backlinks", ["target_domain"])


def downgrade() -> None:
    op.drop_index("ix_discovered_backlinks_target_domain", table_name="discovered_backlinks")
    op.drop_index("ix_discovered_backlinks_source_domain", table_name="discovered_backlinks")
    op.drop_table("discovered_backlinks")
