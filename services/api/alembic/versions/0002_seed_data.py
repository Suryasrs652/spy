"""seed plans (§11), feature flags (§130), rule_config thresholds (§131)

Revision ID: 0002
Revises: 0001
Create Date: 2026-09-10
"""
from __future__ import annotations

import uuid
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql as pg
from sqlalchemy.sql import table, column

revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


PLANS = [
    dict(
        code="FREE", name="Free", price_minor=0, currency="INR",
        billing_interval="ONE_TIME", audit_limit=1, crawl_url_limit=500,
        project_limit=1, member_limit=1,
    ),
    dict(
        code="SINGLE_AUDIT", name="Single Audit", price_minor=29900, currency="INR",
        billing_interval="ONE_TIME", audit_limit=1, crawl_url_limit=2000,
        project_limit=None, member_limit=None,
    ),
    dict(
        code="STARTER", name="Starter", price_minor=79900, currency="INR",
        billing_interval="MONTHLY", audit_limit=5, crawl_url_limit=2000,
        project_limit=5, member_limit=1,
    ),
    dict(
        code="PRO", name="Pro", price_minor=199900, currency="INR",
        billing_interval="MONTHLY", audit_limit=25, crawl_url_limit=10000,
        project_limit=20, member_limit=3,
    ),
    dict(
        code="AGENCY", name="Agency", price_minor=499900, currency="INR",
        billing_interval="MONTHLY", audit_limit=100, crawl_url_limit=25000,
        project_limit=50, member_limit=10,
    ),
]

FEATURE_FLAGS = [
    ("GSC_ENABLED", False),
    ("BACKLINKS_ENABLED", False),
    ("COMMON_CRAWL_ENABLED", False),
    ("AEO_ENABLED", True),
    ("GEO_ENABLED", True),
    ("RANK_TRACKING_ENABLED", False),
    ("JS_RENDER_ENABLED", False),
]

# §131 — versioned rule thresholds read by the SEO rule engine. Bump the
# version string (not these values) when thresholds change so historical
# audits remain reproducible under the methodology they actually ran with.
RULE_CONFIG_VERSION = "rules-v1.0"
RULE_CONFIG = {
    "MIN_TITLE_LENGTH": 15,
    "MAX_TITLE_LENGTH": 60,
    "MIN_DESCRIPTION_LENGTH": 50,
    "MAX_DESCRIPTION_LENGTH": 160,
    "THIN_CONTENT_WORD_THRESHOLD": 150,
    "MAX_CRAWL_DEPTH_WARNING": 4,
    "IMAGE_SIZE_WARNING_BYTES": 300_000,
    "MAX_REDIRECT_CHAIN_LENGTH": 3,
}


def upgrade() -> None:
    plans_table = table(
        "plans",
        column("id", pg.UUID(as_uuid=True)),
        column("code", sa.String),
        column("name", sa.String),
        column("price_minor", sa.BigInteger),
        column("currency", sa.String),
        column("billing_interval", sa.String),
        column("audit_limit", sa.Integer),
        column("crawl_url_limit", sa.Integer),
        column("project_limit", sa.Integer),
        column("member_limit", sa.Integer),
        column("active", sa.Boolean),
    )
    op.bulk_insert(
        plans_table,
        [{"id": uuid.uuid4(), "active": True, **p} for p in PLANS],
    )

    flags_table = table(
        "feature_flags",
        column("key", sa.String),
        column("enabled", sa.Boolean),
        column("config", pg.JSONB),
    )
    op.bulk_insert(
        flags_table,
        [{"key": k, "enabled": v, "config": {}} for k, v in FEATURE_FLAGS],
    )

    import json

    op.execute(
        sa.text(
            "INSERT INTO rule_config (key, version, value, active, created_at, updated_at) "
            "VALUES (:key, :version, CAST(:value AS jsonb), true, now(), now())"
        ).bindparams(
            key="thresholds",
            version=RULE_CONFIG_VERSION,
            value=json.dumps(RULE_CONFIG),
        )
    )


def downgrade() -> None:
    op.execute("DELETE FROM rule_config WHERE key = 'thresholds'")
    op.execute("DELETE FROM feature_flags")
    op.execute("DELETE FROM plans")
