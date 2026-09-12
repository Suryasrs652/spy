"""Record how certain each finding is, and whether anyone has checked it.

`confidence` is declared per rule and backfills to 1.0, which is correct for
the ~80 rules that read a fact straight off the page; the 21 heuristic rules
that carry a lower value only affect audits run after this migration.

`validated` is deliberately nullable. NULL means nobody has checked the
finding against the live site yet — a different statement from False, which
is a recorded verdict that the finding did not hold up. Backfilling either
one over existing rows would be inventing a verdict, so old issues stay NULL.

Revision ID: 0013
Revises: 0012
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0013"
down_revision: str | None = "0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "audit_issues",
        sa.Column("confidence", sa.Numeric(3, 2), nullable=False, server_default="1.0"),
    )
    op.add_column("audit_issues", sa.Column("validated", sa.Boolean(), nullable=True))
    op.add_column(
        "audit_issues", sa.Column("validated_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column("audit_issues", sa.Column("validation_note", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("audit_issues", "validation_note")
    op.drop_column("audit_issues", "validated_at")
    op.drop_column("audit_issues", "validated")
    op.drop_column("audit_issues", "confidence")
