"""Drop billing, entitlements and the sign-in-only user columns.

Spy became a self-hosted, single-user, free tool: there is no sign-up, no
sign-in and nothing metered, so the commercial core (§7-§13) and the
credential columns that only a login flow ever read are gone with the code
that owned them.

Deliberately kept: `users` and `organizations` themselves, plus the
`organization_id` on every tenant table. The app still resolves one fixed
local workspace through them (app/core/local_workspace.py), which is what
lets every query, service and test stay unchanged — and lets real
multi-user auth come back as a change to that one module rather than a
schema-wide rewrite.

Not reversible in the data sense: downgrade recreates the structures, not
the rows that were in them.

Revision ID: 0011
Revises: 0010
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0011"
down_revision: Union[str, None] = "0010"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Order matters: audit_entitlements references users/organizations/audits,
    # subscriptions and purchases reference plans.
    op.drop_table("audit_entitlements")
    op.drop_table("subscriptions")
    op.drop_table("purchases")
    op.drop_table("webhook_events")
    op.drop_table("plans")

    op.drop_constraint("users_google_sub_key", "users", type_="unique")
    op.drop_column("users", "password_hash")
    op.drop_column("users", "google_sub")
    op.drop_column("users", "free_audit_used_at")
    op.drop_column("users", "is_super_admin")


def downgrade() -> None:
    op.add_column("users", sa.Column("is_super_admin", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("users", sa.Column("free_audit_used_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("users", sa.Column("google_sub", sa.String(length=255), nullable=True))
    op.add_column("users", sa.Column("password_hash", sa.String(length=255), nullable=True))
    op.create_unique_constraint("users_google_sub_key", "users", ["google_sub"])

    op.create_table(
        "plans",
        sa.Column("code", sa.String(length=50), primary_key=True),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("price_minor", sa.Integer(), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("billing_interval", sa.String(length=20), nullable=False),
        sa.Column("audit_limit", sa.Integer(), nullable=True),
        sa.Column("crawl_url_limit", sa.Integer(), nullable=False),
        sa.Column("project_limit", sa.Integer(), nullable=True),
        sa.Column("member_limit", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "webhook_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("provider", sa.String(length=50), nullable=False),
        sa.Column("provider_event_id", sa.String(length=200), nullable=False, unique=True),
        sa.Column("event_type", sa.String(length=100), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_table(
        "purchases",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("provider", sa.String(length=50), nullable=False),
        sa.Column("provider_order_id", sa.String(length=200), nullable=False),
        sa.Column("provider_payment_id", sa.String(length=200), nullable=True),
        sa.Column("product_type", sa.String(length=50), nullable=False),
        sa.Column("plan_code", sa.String(length=50), sa.ForeignKey("plans.code"), nullable=True),
        sa.Column("amount_minor", sa.Integer(), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("paid_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "subscriptions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("plan_code", sa.String(length=50), sa.ForeignKey("plans.code"), nullable=False),
        sa.Column("provider_subscription_id", sa.String(length=200), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("current_period_start", sa.DateTime(timezone=True), nullable=True),
        sa.Column("current_period_end", sa.DateTime(timezone=True), nullable=True),
        sa.Column("audits_used_this_period", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "audit_entitlements",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("type", sa.String(length=20), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("audit_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("audits.id", ondelete="SET NULL"), nullable=True),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("remaining", sa.Integer(), nullable=False),
        sa.Column("source", sa.String(length=100), nullable=False),
        sa.Column("reserved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.execute(
        """
        CREATE UNIQUE INDEX uq_free_entitlement_live
          ON audit_entitlements (user_id)
          WHERE type = 'FREE_LIFETIME'
            AND status IN ('AVAILABLE','RESERVED','CONSUMED')
        """
    )
