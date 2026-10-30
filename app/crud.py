"""Database access layer — keeps SQL out of the routers."""
from __future__ import annotations

from datetime import date, datetime, time, timedelta

from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from .models import AdminUser, Lead, utcnow
from .schemas import LeadCreate
from .security import hash_password


# ---------------------------------------------------------------------------
# Leads
# ---------------------------------------------------------------------------
def create_lead(db: Session, payload: LeadCreate, *, status: str, ip_hash: str | None) -> Lead:
    data = payload.model_dump(exclude={"fax"})
    crm_status = "skipped" if status == "spam" else "pending"
    lead = Lead(**data, status=status, crm_sync_status=crm_status, ip_hash=ip_hash)
    db.add(lead)
    db.commit()
    db.refresh(lead)
    return lead


def get_lead(db: Session, lead_id: str) -> Lead | None:
    return db.get(Lead, lead_id)


def get_by_submission_id(db: Session, submission_id: str) -> Lead | None:
    return db.query(Lead).filter(Lead.submission_id == submission_id).first()


def find_duplicate(db: Session, *, customer_name: str, window_hours: int) -> Lead | None:
    """A non-spam record with the same customer name submitted within the window.

    NOTE: the CRM entity has no email/phone column, so exact-name matching is
    the strongest duplicate signal available. Add a contact field to the CRM
    entity if stronger deduplication is needed.
    """
    cutoff = utcnow() - timedelta(hours=window_hours)
    return (
        db.query(Lead)
        .filter(
            func.lower(Lead.customer_name) == customer_name.lower(),
            Lead.status != "spam",
            Lead.submitted_at >= cutoff,
        )
        .order_by(Lead.submitted_at.desc())
        .first()
    )


def list_leads(
    db: Session,
    *,
    q: str | None = None,
    status: str | None = None,
    stage: str | None = None,
    sync_status: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    page: int = 1,
    page_size: int = 20,
) -> tuple[list[Lead], int]:
    query = db.query(Lead)
    if q:
        like = f"%{q.strip()}%"
        query = query.filter(
            or_(
                Lead.customer_name.ilike(like),
                Lead.reference.ilike(like),
                Lead.customer_segment.ilike(like),
            )
        )
    if status:
        query = query.filter(Lead.status == status)
    if stage:
        query = query.filter(Lead.crm_status == stage)
    if sync_status:
        query = query.filter(Lead.crm_sync_status == sync_status)
    if date_from:
        query = query.filter(Lead.submitted_at >= datetime.combine(date_from, time.min))
    if date_to:
        query = query.filter(Lead.submitted_at < datetime.combine(date_to + timedelta(days=1), time.min))

    total = query.count()
    items = (
        query.order_by(Lead.submitted_at.desc())
        .offset((max(page, 1) - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return items, total


def stats(db: Session) -> dict:
    not_spam = Lead.status != "spam"
    total = db.query(func.count(Lead.id)).filter(not_spam).scalar() or 0
    synced = db.query(func.count(Lead.id)).filter(not_spam, Lead.crm_sync_status == "synced").scalar() or 0
    pending = db.query(func.count(Lead.id)).filter(not_spam, Lead.crm_sync_status == "pending").scalar() or 0
    failed = db.query(func.count(Lead.id)).filter(not_spam, Lead.crm_sync_status == "failed").scalar() or 0
    spam = db.query(func.count(Lead.id)).filter(Lead.status == "spam").scalar() or 0
    start_of_today = datetime.combine(utcnow().date(), time.min)
    today = db.query(func.count(Lead.id)).filter(not_spam, Lead.submitted_at >= start_of_today).scalar() or 0
    return {
        "total_leads": total,
        "synced": synced,
        "pending": pending,
        "failed": failed,
        "spam": spam,
        "today": today,
    }


def leads_pending_sync(db: Session, *, limit: int = 200) -> list[Lead]:
    return (
        db.query(Lead)
        .filter(Lead.status != "spam", Lead.crm_sync_status.in_(["pending", "failed"]))
        .order_by(Lead.submitted_at.asc())
        .limit(limit)
        .all()
    )


# ---------------------------------------------------------------------------
# Admin users
# ---------------------------------------------------------------------------
def get_admin_by_email(db: Session, email: str) -> AdminUser | None:
    return db.query(AdminUser).filter(AdminUser.email == email.lower()).first()


def create_admin(db: Session, *, email: str, password: str, role: str = "admin") -> AdminUser:
    user = AdminUser(email=email.lower(), password_hash=hash_password(password), role=role)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user
