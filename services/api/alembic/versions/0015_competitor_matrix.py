"""Store enough about a competitor benchmark to put it in a matrix.

`score_version` is the important one: a competitor benchmarked under an older
scoring version is not comparable to a current audit, for the same reason two
audits under different versions are not (§22). Existing rows are backfilled to
spy-score-v1.0 because that is what they were scored under — leaving them NULL
would read as "comparable" and quietly mix two meanings of `seo_score` in one
table.

Revision ID: 0015
Revises: 0014
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0015"
down_revision: str | None = "0014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("competitors", sa.Column("score_version", sa.String(30), nullable=True))
    op.add_column("competitors", sa.Column("acrs_score", sa.Numeric(5, 2), nullable=True))
    op.add_column("competitors", sa.Column("internal_links_score", sa.Numeric(5, 2), nullable=True))
    op.add_column("competitors", sa.Column("structured_data_score", sa.Numeric(5, 2), nullable=True))
    op.execute(
        "UPDATE competitors SET score_version = 'spy-score-v1.0' "
        "WHERE score_version IS NULL AND spy_score IS NOT NULL"
    )


def downgrade() -> None:
    op.drop_column("competitors", "structured_data_score")
    op.drop_column("competitors", "internal_links_score")
    op.drop_column("competitors", "acrs_score")
    op.drop_column("competitors", "score_version")
