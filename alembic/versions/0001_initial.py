"""Initial schema: leads, admin_users, sync_logs.

Revision ID: 0001_initial
Revises:
Create Date: 2026-10-30
"""
from alembic import op
import sqlalchemy as sa

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "leads",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("reference", sa.String(length=20), nullable=False),
        sa.Column("full_name", sa.String(length=120), nullable=False),
        sa.Column("email", sa.String(length=254), nullable=False),
        sa.Column("phone", sa.String(length=25), nullable=False),
        sa.Column("company_name", sa.String(length=160), nullable=False),
        sa.Column("job_title", sa.String(length=120), nullable=False),
        sa.Column("industry", sa.String(length=80), nullable=False),
        sa.Column("industry_other", sa.String(length=120), nullable=True),
        sa.Column("company_size", sa.String(length=40), nullable=False),
        sa.Column("location", sa.String(length=160), nullable=False),
        sa.Column("website_url", sa.String(length=300), nullable=True),
        sa.Column("product_interest", sa.String(length=120), nullable=False),
        sa.Column("requirement_type", sa.String(length=60), nullable=False),
        sa.Column("budget", sa.String(length=60), nullable=True),
        sa.Column("timeline", sa.String(length=60), nullable=False),
        sa.Column("message", sa.Text(), nullable=True),
        sa.Column("consent_privacy", sa.Boolean(), nullable=False),
        sa.Column("consent_contact", sa.Boolean(), nullable=False),
        sa.Column("consent_marketing", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("source", sa.String(length=60), nullable=False, server_default="website"),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="new"),
        sa.Column("crm_sync_status", sa.String(length=20), nullable=False, server_default="pending"),
        sa.Column("crm_lead_id", sa.String(length=120), nullable=True),
        sa.Column("crm_error", sa.String(length=500), nullable=True),
        sa.Column("crm_attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("submission_id", sa.String(length=64), nullable=True),
        sa.Column("ip_hash", sa.String(length=64), nullable=True),
        sa.Column("submitted_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("reference", name="uq_leads_reference"),
        sa.UniqueConstraint("submission_id", name="uq_leads_submission_id"),
    )
    op.create_index("ix_leads_reference", "leads", ["reference"])
    op.create_index("ix_leads_email", "leads", ["email"])
    op.create_index("ix_leads_status", "leads", ["status"])
    op.create_index("ix_leads_crm_sync_status", "leads", ["crm_sync_status"])
    op.create_index("ix_leads_submitted_at", "leads", ["submitted_at"])

    op.create_table(
        "admin_users",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("email", sa.String(length=254), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("role", sa.String(length=20), nullable=False, server_default="admin"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("email", name="uq_admin_users_email"),
    )
    op.create_index("ix_admin_users_email", "admin_users", ["email"])

    op.create_table(
        "sync_logs",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("lead_id", sa.String(length=36), sa.ForeignKey("leads.id"), nullable=False),
        sa.Column("attempt", sa.Integer(), nullable=False),
        sa.Column("success", sa.Boolean(), nullable=False),
        sa.Column("status_code", sa.Integer(), nullable=True),
        sa.Column("error", sa.String(length=500), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_sync_logs_lead_id", "sync_logs", ["lead_id"])


def downgrade() -> None:
    op.drop_table("sync_logs")
    op.drop_table("admin_users")
    op.drop_table("leads")
