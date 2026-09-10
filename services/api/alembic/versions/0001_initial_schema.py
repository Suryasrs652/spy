"""initial schema — users, organizations, projects, entitlements, audits,
crawler, seo, recommendations, reports, billing, gsc, admin/infra

Revision ID: 0001
Revises:
Create Date: 2026-09-10
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql as pg

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute('CREATE EXTENSION IF NOT EXISTS "uuid-ossp"')

    # ── users ────────────────────────────────────────────────────────
    op.create_table(
        "users",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("email", sa.String(320), nullable=False, unique=True),
        sa.Column("password_hash", sa.String(255), nullable=True),
        sa.Column("email_verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="ACTIVE"),
        sa.Column("free_audit_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("google_sub", sa.String(255), nullable=True, unique=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_users_email", "users", ["email"])

    # ── organizations ────────────────────────────────────────────────
    op.create_table(
        "organizations",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("slug", sa.String(220), nullable=False, unique=True),
        sa.Column("owner_user_id", pg.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_organizations_slug", "organizations", ["slug"])

    op.create_table(
        "organization_members",
        sa.Column("organization_id", pg.UUID(as_uuid=True), sa.ForeignKey("organizations.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("user_id", pg.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("role", sa.String(20), nullable=False, server_default="OWNER"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )

    # ── projects ─────────────────────────────────────────────────────
    op.create_table(
        "projects",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", pg.UUID(as_uuid=True), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("domain", sa.String(255), nullable=False),
        sa.Column("canonical_origin", sa.Text(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="ACTIVE"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("organization_id", "canonical_origin", name="uq_project_org_origin"),
    )
    op.create_index("ix_projects_organization_id", "projects", ["organization_id"])

    # ── plans (§80 — seeded below, editable via admin) ──────────────
    op.create_table(
        "plans",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("code", sa.String(30), nullable=False, unique=True),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("price_minor", sa.BigInteger(), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False, server_default="INR"),
        sa.Column("billing_interval", sa.String(20), nullable=False),
        sa.Column("audit_limit", sa.Integer(), nullable=True),
        sa.Column("crawl_url_limit", sa.Integer(), nullable=False, server_default="500"),
        sa.Column("project_limit", sa.Integer(), nullable=True),
        sa.Column("member_limit", sa.Integer(), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
    )

    # ── audits ───────────────────────────────────────────────────────
    op.create_table(
        "audits",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", pg.UUID(as_uuid=True), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("project_id", pg.UUID(as_uuid=True), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("requested_by", pg.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("audit_type", sa.String(30), nullable=False, server_default="FULL"),
        sa.Column("status", sa.String(30), nullable=False, server_default="QUEUED"),
        sa.Column("max_urls", sa.Integer(), nullable=False, server_default="500"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("spy_score", sa.Numeric(5, 2), nullable=True),
        sa.Column("technical_score", sa.Numeric(5, 2), nullable=True),
        sa.Column("seo_score", sa.Numeric(5, 2), nullable=True),
        sa.Column("content_score", sa.Numeric(5, 2), nullable=True),
        sa.Column("performance_score", sa.Numeric(5, 2), nullable=True),
        sa.Column("authority_score", sa.Numeric(5, 2), nullable=True),
        sa.Column("aeo_score", sa.Numeric(5, 2), nullable=True),
        sa.Column("geo_score", sa.Numeric(5, 2), nullable=True),
        sa.Column("confidence", sa.Numeric(5, 2), nullable=True),
        sa.Column("evidence", pg.JSONB(), nullable=False, server_default="{}"),
        sa.Column("score_version", sa.String(30), nullable=False, server_default="spy-score-v1.0"),
        sa.Column("failure_category", sa.String(30), nullable=True),
        sa.Column("failure_code", sa.String(50), nullable=True),
        sa.Column("failure_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_audits_organization_id", "audits", ["organization_id"])
    op.create_index("ix_audits_project_id", "audits", ["project_id"])

    # ── audit_entitlements (§8 race prevention) ─────────────────────
    op.create_table(
        "audit_entitlements",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", pg.UUID(as_uuid=True), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", pg.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("type", sa.String(20), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="AVAILABLE"),
        sa.Column("audit_id", pg.UUID(as_uuid=True), sa.ForeignKey("audits.id", ondelete="SET NULL"), nullable=True),
        sa.Column("quantity", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("remaining", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("source", sa.String(100), nullable=False, server_default="SYSTEM"),
        sa.Column("reserved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_audit_entitlements_organization_id", "audit_entitlements", ["organization_id"])
    op.create_index("ix_audit_entitlements_user_id", "audit_entitlements", ["user_id"])
    # §7/§8/§157: the load-bearing constraint. At most one "live" FREE_LIFETIME
    # row can exist per user — this is what makes 20 concurrent clicks yield
    # exactly one free audit, enforced by Postgres, not application code.
    op.execute(
        "CREATE UNIQUE INDEX uq_free_entitlement_live "
        "ON audit_entitlements (user_id) "
        "WHERE type = 'FREE_LIFETIME' "
        "AND status IN ('AVAILABLE','RESERVED','CONSUMED')"
    )

    # ── audit_jobs ───────────────────────────────────────────────────
    op.create_table(
        "audit_jobs",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("audit_id", pg.UUID(as_uuid=True), sa.ForeignKey("audits.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("status", sa.String(30), nullable=False, server_default="QUEUED"),
        sa.Column("progress", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("urls_discovered", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("urls_processed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("queue_job_id", sa.String(100), nullable=True),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_code", sa.String(50), nullable=True),
        sa.Column("error_detail", sa.Text(), nullable=True),
    )

    # ── crawl_pages / page_links ─────────────────────────────────────
    op.create_table(
        "crawl_pages",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("audit_id", pg.UUID(as_uuid=True), sa.ForeignKey("audits.id", ondelete="CASCADE"), nullable=False),
        sa.Column("project_id", pg.UUID(as_uuid=True), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("normalized_url", sa.Text(), nullable=False),
        sa.Column("status_code", sa.Integer(), nullable=True),
        sa.Column("content_type", sa.String(120), nullable=True),
        sa.Column("title", sa.Text(), nullable=True),
        sa.Column("meta_description", sa.Text(), nullable=True),
        sa.Column("h1", sa.Text(), nullable=True),
        sa.Column("canonical_url", sa.Text(), nullable=True),
        sa.Column("robots_meta", sa.String(255), nullable=True),
        sa.Column("word_count", sa.Integer(), nullable=True),
        sa.Column("content_hash", sa.String(64), nullable=True),
        sa.Column("html_hash", sa.String(64), nullable=True),
        sa.Column("crawl_depth", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("indexable", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("robots_allowed", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("response_ms", sa.Integer(), nullable=True),
        sa.Column("html_size", sa.BigInteger(), nullable=True),
        sa.Column("redirect_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("h1_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("images_total", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("images_missing_alt", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("has_schema", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("schema_types", pg.ARRAY(sa.String()), nullable=False, server_default="{}"),
        sa.Column("schema_invalid", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("mixed_content", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_crawl_pages_audit_id", "crawl_pages", ["audit_id"])
    op.create_index("ix_crawl_pages_project_id", "crawl_pages", ["project_id"])
    op.create_index("ix_crawl_pages_normalized_url", "crawl_pages", ["normalized_url"])
    op.create_index("ix_crawl_pages_status_code", "crawl_pages", ["status_code"])
    op.create_index("ix_crawl_pages_indexable", "crawl_pages", ["indexable"])

    op.create_table(
        "page_links",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("audit_id", pg.UUID(as_uuid=True), sa.ForeignKey("audits.id", ondelete="CASCADE"), nullable=False),
        sa.Column("source_page_id", pg.UUID(as_uuid=True), sa.ForeignKey("crawl_pages.id", ondelete="CASCADE"), nullable=False),
        sa.Column("target_url", sa.Text(), nullable=False),
        sa.Column("target_page_id", pg.UUID(as_uuid=True), sa.ForeignKey("crawl_pages.id", ondelete="SET NULL"), nullable=True),
        sa.Column("anchor_text", sa.Text(), nullable=True),
        sa.Column("is_internal", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("nofollow", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("ugc", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("sponsored", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("status_code", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_page_links_audit_id", "page_links", ["audit_id"])
    op.create_index("ix_page_links_source_page_id", "page_links", ["source_page_id"])

    # ── audit_issues / audit_issue_pages ─────────────────────────────
    op.create_table(
        "audit_issues",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("audit_id", pg.UUID(as_uuid=True), sa.ForeignKey("audits.id", ondelete="CASCADE"), nullable=False),
        sa.Column("rule_id", sa.String(50), nullable=False),
        sa.Column("category", sa.String(50), nullable=False),
        sa.Column("severity", sa.String(20), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("recommendation", sa.Text(), nullable=False),
        sa.Column("affected_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("score_impact", sa.Numeric(5, 2), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_audit_issues_audit_id", "audit_issues", ["audit_id"])
    op.create_index("ix_audit_issues_rule_id", "audit_issues", ["rule_id"])

    op.create_table(
        "audit_issue_pages",
        sa.Column("issue_id", pg.UUID(as_uuid=True), sa.ForeignKey("audit_issues.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("page_id", pg.UUID(as_uuid=True), sa.ForeignKey("crawl_pages.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("evidence", pg.JSONB(), nullable=False, server_default="{}"),
    )

    # ── recommendations ──────────────────────────────────────────────
    op.create_table(
        "recommendations",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("audit_id", pg.UUID(as_uuid=True), sa.ForeignKey("audits.id", ondelete="CASCADE"), nullable=False),
        sa.Column("category", sa.String(50), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("impact", sa.Integer(), nullable=False),
        sa.Column("confidence", sa.Integer(), nullable=False),
        sa.Column("effort", sa.Integer(), nullable=False),
        sa.Column("priority_score", sa.Numeric(5, 2), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="OPEN"),
        sa.Column("group", sa.String(20), nullable=False, server_default="MONITOR"),
        sa.Column("evidence", pg.JSONB(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_recommendations_audit_id", "recommendations", ["audit_id"])

    # ── reports ──────────────────────────────────────────────────────
    op.create_table(
        "reports",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("audit_id", pg.UUID(as_uuid=True), sa.ForeignKey("audits.id", ondelete="CASCADE"), nullable=False),
        sa.Column("organization_id", pg.UUID(as_uuid=True), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("format", sa.String(10), nullable=False, server_default="PDF"),
        sa.Column("storage_key", sa.Text(), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="PENDING"),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_reports_audit_id", "reports", ["audit_id"])
    op.create_index("ix_reports_organization_id", "reports", ["organization_id"])

    # ── subscriptions / purchases / webhook_events ──────────────────
    op.create_table(
        "subscriptions",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", pg.UUID(as_uuid=True), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("provider", sa.String(30), nullable=False, server_default="razorpay"),
        sa.Column("provider_subscription_id", sa.String(100), nullable=False, unique=True),
        sa.Column("plan_id", pg.UUID(as_uuid=True), sa.ForeignKey("plans.id"), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="ACTIVE"),
        sa.Column("current_period_start", sa.DateTime(timezone=True), nullable=True),
        sa.Column("current_period_end", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancel_at_period_end", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_subscriptions_organization_id", "subscriptions", ["organization_id"])

    op.create_table(
        "purchases",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", pg.UUID(as_uuid=True), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("provider", sa.String(30), nullable=False, server_default="razorpay"),
        sa.Column("provider_order_id", sa.String(100), nullable=False),
        sa.Column("provider_payment_id", sa.String(100), nullable=True),
        sa.Column("product_type", sa.String(30), nullable=False, server_default="SINGLE_AUDIT"),
        sa.Column("amount_minor", sa.BigInteger(), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False, server_default="INR"),
        sa.Column("status", sa.String(20), nullable=False, server_default="PENDING"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("paid_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_purchases_organization_id", "purchases", ["organization_id"])
    op.create_index("ix_purchases_provider_order_id", "purchases", ["provider_order_id"])

    op.create_table(
        "webhook_events",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("provider", sa.String(30), nullable=False),
        sa.Column("provider_event_id", sa.String(150), nullable=False, unique=True),
        sa.Column("event_type", sa.String(50), nullable=False),
        sa.Column("payload", pg.JSONB(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="RECEIVED"),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
    )

    # ── GSC ──────────────────────────────────────────────────────────
    op.create_table(
        "gsc_connections",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", pg.UUID(as_uuid=True), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", pg.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("google_account_id", sa.String(100), nullable=False),
        sa.Column("encrypted_refresh_token", sa.Text(), nullable=False),
        sa.Column("scopes", pg.ARRAY(sa.String()), nullable=False, server_default="{}"),
        sa.Column("status", sa.String(20), nullable=False, server_default="ACTIVE"),
        sa.Column("connected_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_sync_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_gsc_connections_organization_id", "gsc_connections", ["organization_id"])

    op.create_table(
        "gsc_properties",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("connection_id", pg.UUID(as_uuid=True), sa.ForeignKey("gsc_connections.id", ondelete="CASCADE"), nullable=False),
        sa.Column("project_id", pg.UUID(as_uuid=True), sa.ForeignKey("projects.id", ondelete="SET NULL"), nullable=True),
        sa.Column("site_url", sa.Text(), nullable=False),
        sa.Column("permission_level", sa.String(30), nullable=False),
        sa.Column("selected", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_gsc_properties_connection_id", "gsc_properties", ["connection_id"])

    op.create_table(
        "gsc_daily_metrics",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("property_id", pg.UUID(as_uuid=True), sa.ForeignKey("gsc_properties.id", ondelete="CASCADE"), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("query", sa.Text(), nullable=True),
        sa.Column("page", sa.Text(), nullable=True),
        sa.Column("country", sa.String(10), nullable=True),
        sa.Column("device", sa.String(20), nullable=True),
        sa.Column("search_type", sa.String(20), nullable=False, server_default="web"),
        sa.Column("clicks", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("impressions", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("ctr", sa.Numeric(6, 4), nullable=False, server_default="0"),
        sa.Column("position", sa.Numeric(6, 2), nullable=False, server_default="0"),
    )
    op.create_index("ix_gsc_daily_metrics_property_id", "gsc_daily_metrics", ["property_id"])
    op.create_index("ix_gsc_daily_metrics_date", "gsc_daily_metrics", ["date"])

    # ── admin / infra ────────────────────────────────────────────────
    op.create_table(
        "feature_flags",
        sa.Column("key", sa.String(50), primary_key=True),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("config", pg.JSONB(), nullable=False, server_default="{}"),
    )

    op.create_table(
        "rule_config",
        sa.Column("key", sa.String(100), primary_key=True),
        sa.Column("version", sa.String(30), primary_key=True),
        sa.Column("value", pg.JSONB(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "audit_logs",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("organization_id", pg.UUID(as_uuid=True), nullable=True),
        sa.Column("user_id", pg.UUID(as_uuid=True), nullable=True),
        sa.Column("action", sa.String(100), nullable=False),
        sa.Column("entity_type", sa.String(50), nullable=False),
        sa.Column("entity_id", sa.String(100), nullable=False),
        sa.Column("ip_hash", sa.String(64), nullable=True),
        sa.Column("metadata", pg.JSONB(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_audit_logs_organization_id", "audit_logs", ["organization_id"])
    op.create_index("ix_audit_logs_user_id", "audit_logs", ["user_id"])

    op.create_table(
        "idempotency_keys",
        sa.Column("key", sa.String(200), primary_key=True),
        sa.Column("organization_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("endpoint", sa.String(200), nullable=False),
        sa.Column("response_status", sa.Integer(), nullable=False),
        sa.Column("response_body", pg.JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("idempotency_keys")
    op.drop_table("audit_logs")
    op.drop_table("rule_config")
    op.drop_table("feature_flags")
    op.drop_table("gsc_daily_metrics")
    op.drop_table("gsc_properties")
    op.drop_table("gsc_connections")
    op.drop_table("webhook_events")
    op.drop_table("purchases")
    op.drop_table("subscriptions")
    op.drop_table("reports")
    op.drop_table("recommendations")
    op.drop_table("audit_issue_pages")
    op.drop_table("audit_issues")
    op.drop_table("page_links")
    op.drop_table("crawl_pages")
    op.drop_table("audit_jobs")
    op.execute("DROP INDEX IF EXISTS uq_free_entitlement_live")
    op.drop_table("audit_entitlements")
    op.drop_table("audits")
    op.drop_table("plans")
    op.drop_table("projects")
    op.drop_table("organization_members")
    op.drop_table("organizations")
    op.drop_table("users")
