"""SQLAlchemy ORM models: Lead, AdminUser, SyncLog."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


def utcnow() -> datetime:
    """Naive UTC timestamp — portable across SQLite and PostgreSQL."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def generate_reference() -> str:
    """Human-friendly public lead reference shown to the prospect."""
    return f"AUR-{uuid.uuid4().hex[:8].upper()}"


# Pipeline stages configured in the AURA CRM (Analytical_E_Commerce_CRM).
PIPELINE_STAGES = ("New", "Analyzing", "High Value", "At Risk", "Retained/Lost")


class Lead(Base):
    __tablename__ = "leads"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    reference: Mapped[str] = mapped_column(String(20), unique=True, index=True, default=generate_reference)

    # --- CRM entity fields (Machine Identifier, 6 required dynamic fields) ---
    customer_name: Mapped[str] = mapped_column(String(160))
    customer_segment: Mapped[str] = mapped_column(String(80))
    total_revenue: Mapped[float] = mapped_column(Float)
    purchase_frequency: Mapped[int] = mapped_column(Integer)
    customer_value: Mapped[float] = mapped_column(Float)
    crm_status: Mapped[str] = mapped_column(String(40), default="New", index=True)  # pipeline stage

    # --- Consent (local compliance record — not part of the CRM entity) ---
    consent_privacy: Mapped[bool] = mapped_column(Boolean)
    consent_contact: Mapped[bool] = mapped_column(Boolean)
    consent_marketing: Mapped[bool] = mapped_column(Boolean, default=False)

    # --- Metadata ---
    source: Mapped[str] = mapped_column(String(60), default="Website")
    status: Mapped[str] = mapped_column(String(20), default="new", index=True)  # internal: new | spam
    crm_sync_status: Mapped[str] = mapped_column(String(20), default="pending", index=True)
    #   pending | synced | failed | skipped (spam) | disabled (no CRM configured)
    crm_lead_id: Mapped[str | None] = mapped_column(String(120))
    crm_error: Mapped[str | None] = mapped_column(String(500))
    crm_attempts: Mapped[int] = mapped_column(Integer, default=0)
    submission_id: Mapped[str | None] = mapped_column(String(64), unique=True)  # idempotency key from client
    ip_hash: Mapped[str | None] = mapped_column(String(64))  # hashed, never stored raw
    submitted_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)

    sync_logs: Mapped[list["SyncLog"]] = relationship(
        back_populates="lead", cascade="all, delete-orphan", order_by="SyncLog.created_at"
    )

    def to_dict(self) -> dict:
        return {column.name: getattr(self, column.name) for column in self.__table__.columns}


class AdminUser(Base):
    __tablename__ = "admin_users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    email: Mapped[str] = mapped_column(String(254), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(20), default="admin")  # admin | viewer
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class SyncLog(Base):
    """Audit trail of every CRM synchronization attempt."""

    __tablename__ = "sync_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    lead_id: Mapped[str] = mapped_column(String(36), ForeignKey("leads.id"), index=True)
    attempt: Mapped[int] = mapped_column(Integer)
    success: Mapped[bool] = mapped_column(Boolean)
    status_code: Mapped[int | None] = mapped_column(Integer)
    error: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    lead: Mapped[Lead] = relationship(back_populates="sync_logs")
