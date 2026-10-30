"""Align leads with the AURA CRM 'Machine Identifier' entity.

Replaces the generic lead-capture columns with the CRM's 6 dynamic fields:
customer_name, customer_segment, total_revenue, purchase_frequency,
customer_value, crm_status. (Dev-stage migration: existing generic lead
rows are not migrated — wipe dev databases or downgrade first if needed.)

Revision ID: 0002_crm_aligned_leads
Revises: 0001_initial
Create Date: 2026-10-30
"""
from alembic import op
import sqlalchemy as sa

revision = "0002_crm_aligned_leads"
down_revision = "0001_initial"
branch_labels = None
depends_on = None

_OLD_COLUMNS = [
    "full_name", "email", "phone", "company_name", "job_title", "industry",
    "industry_other", "company_size", "location", "website_url",
    "product_interest", "requirement_type", "budget", "timeline", "message",
]


def upgrade() -> None:
    op.drop_index("ix_leads_email", table_name="leads")
    with op.batch_alter_table("leads") as batch:
        for column in _OLD_COLUMNS:
            batch.drop_column(column)
        batch.add_column(sa.Column("customer_name", sa.String(length=160), nullable=False, server_default=""))
        batch.add_column(sa.Column("customer_segment", sa.String(length=80), nullable=False, server_default=""))
        batch.add_column(sa.Column("total_revenue", sa.Float(), nullable=False, server_default="0"))
        batch.add_column(sa.Column("purchase_frequency", sa.Integer(), nullable=False, server_default="0"))
        batch.add_column(sa.Column("customer_value", sa.Float(), nullable=False, server_default="0"))
        batch.add_column(sa.Column("crm_status", sa.String(length=40), nullable=False, server_default="New"))
    op.create_index("ix_leads_crm_status", "leads", ["crm_status"])
    op.alter_column("leads", "source", server_default="Website")


def downgrade() -> None:
    op.drop_index("ix_leads_crm_status", table_name="leads")
    with op.batch_alter_table("leads") as batch:
        for column in ("customer_name", "customer_segment", "total_revenue", "purchase_frequency", "customer_value", "crm_status"):
            batch.drop_column(column)
        batch.add_column(sa.Column("full_name", sa.String(length=120), nullable=False, server_default=""))
        batch.add_column(sa.Column("email", sa.String(length=254), nullable=False, server_default=""))
        batch.add_column(sa.Column("phone", sa.String(length=25), nullable=False, server_default=""))
        batch.add_column(sa.Column("company_name", sa.String(length=160), nullable=False, server_default=""))
        batch.add_column(sa.Column("job_title", sa.String(length=120), nullable=False, server_default=""))
        batch.add_column(sa.Column("industry", sa.String(length=80), nullable=False, server_default=""))
        batch.add_column(sa.Column("industry_other", sa.String(length=120), nullable=True))
        batch.add_column(sa.Column("company_size", sa.String(length=40), nullable=False, server_default=""))
        batch.add_column(sa.Column("location", sa.String(length=160), nullable=False, server_default=""))
        batch.add_column(sa.Column("website_url", sa.String(length=300), nullable=True))
        batch.add_column(sa.Column("product_interest", sa.String(length=120), nullable=False, server_default=""))
        batch.add_column(sa.Column("requirement_type", sa.String(length=60), nullable=False, server_default=""))
        batch.add_column(sa.Column("budget", sa.String(length=60), nullable=True))
        batch.add_column(sa.Column("timeline", sa.String(length=60), nullable=False, server_default=""))
        batch.add_column(sa.Column("message", sa.Text(), nullable=True))
    op.create_index("ix_leads_email", "leads", ["email"])
