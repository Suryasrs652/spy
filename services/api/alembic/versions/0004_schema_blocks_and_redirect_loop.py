"""M2: full schema-block storage (for field-level Organization/Person/FAQ
validation and GEO entity scoring) + redirect-loop detection

Revision ID: 0004
Revises: 0003
Create Date: 2026-09-10
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql as pg

revision: str = "0004"
down_revision: Union[str, None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Full parsed JSON-LD blocks (capped at extraction time, §schema
    # validation) — schema_types alone (added in 0001) only carries the
    # @type name, not enough to check required fields (e.g. Organization
    # missing "name"/"url"/"logo") or to feed GEO's entity-clarity scoring.
    op.add_column("crawl_pages", sa.Column("schema_blocks", pg.JSONB(), nullable=False, server_default="[]"))
    op.add_column(
        "crawl_pages", sa.Column("is_redirect_loop", sa.Boolean(), nullable=False, server_default=sa.false())
    )


def downgrade() -> None:
    op.drop_column("crawl_pages", "is_redirect_loop")
    op.drop_column("crawl_pages", "schema_blocks")
