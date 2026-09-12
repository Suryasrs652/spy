"""Split the composite into SEO / AEO / GEO, and SEO into seven components.

Three new columns hold the SEO components that previously had nowhere to
live: on-page, internal links and structured data. `onpage_score` is where
the old `seo_score` value belongs — under spy-score-v1.0 that column held the
on-page score (metadata + images + schema) despite its name, and under v2.0
it holds the seven-component SEO score.

Existing rows are backfilled by *moving* the old value into `onpage_score`,
not by recomputing: a completed audit's score is immutable (§22/§132), and
the crawl evidence a v2.0 score needs is not all present on older audits
anyway. `seo_score`, `spy_score`, `aeo_score` and `geo_score` on those rows
keep their v1.0 meaning, which is why `score_version` is stored per audit and
why comparing across versions is refused rather than silently performed.

Revision ID: 0014
Revises: 0013
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0014"
down_revision: str | None = "0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("audits", sa.Column("onpage_score", sa.Numeric(5, 2), nullable=True))
    op.add_column("audits", sa.Column("internal_links_score", sa.Numeric(5, 2), nullable=True))
    op.add_column("audits", sa.Column("structured_data_score", sa.Numeric(5, 2), nullable=True))

    # v1.0's `seo_score` was the on-page score. Move it, so the column that
    # says "on-page" holds the on-page number on every row regardless of
    # which version produced it.
    op.execute(
        "UPDATE audits SET onpage_score = seo_score "
        "WHERE score_version = 'spy-score-v1.0' AND seo_score IS NOT NULL"
    )

    # v1.0 kept the internal-architecture sub-score only in the evidence
    # blob, because it had no column. It has one now.
    op.execute(
        "UPDATE audits SET internal_links_score = (evidence->>'architecture_score')::numeric "
        "WHERE score_version = 'spy-score-v1.0' "
        "AND jsonb_typeof(evidence->'architecture_score') = 'number'"
    )

    op.add_column(
        "competitors", sa.Column("onpage_score", sa.Numeric(5, 2), nullable=True)
    )
    op.execute("UPDATE competitors SET onpage_score = seo_score WHERE seo_score IS NOT NULL")


def downgrade() -> None:
    op.drop_column("competitors", "onpage_score")
    op.drop_column("audits", "structured_data_score")
    op.drop_column("audits", "internal_links_score")
    op.drop_column("audits", "onpage_score")
