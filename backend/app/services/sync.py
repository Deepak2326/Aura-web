"""CRM synchronization service.

Guarantees:
  - a submitted lead is NEVER lost because the CRM is down — it stays in the
    local database with status pending/failed and can be retried;
  - every attempt is audited in sync_logs;
  - errors stored on the lead never contain credentials or request payloads.
"""
from __future__ import annotations

import logging
import time
from datetime import datetime

from sqlalchemy.orm import Session, sessionmaker

from ..config import Settings
from ..crm.base import CRMClient
from ..models import Lead, SyncLog

logger = logging.getLogger("aura.sync")


def serialize_lead(lead: Lead) -> dict:
    """Plain-JSON representation of a lead (datetimes -> ISO 8601 strings)."""
    data = lead.to_dict()
    for key, value in data.items():
        if isinstance(value, datetime):
            data[key] = value.isoformat() + "Z"
    return data


def sync_lead(
    db: Session,
    lead: Lead,
    client: CRMClient,
    *,
    max_attempts: int,
    backoff_seconds: float,
) -> Lead:
    """Attempt to push a lead to the CRM with retries + exponential backoff."""
    if client.name == "null":
        lead.crm_sync_status = "disabled"
        db.commit()
        return lead

    payload = client.build_payload(serialize_lead(lead))
    delay = backoff_seconds

    for _ in range(max(1, max_attempts)):
        result = client.create_lead(payload)
        lead.crm_attempts += 1
        db.add(
            SyncLog(
                lead_id=lead.id,
                attempt=lead.crm_attempts,
                success=result.success,
                status_code=result.status_code,
                error=result.error,
            )
        )
        if result.success:
            lead.crm_sync_status = "synced"
            lead.crm_lead_id = result.crm_lead_id
            lead.crm_error = None
            db.commit()
            logger.info("Lead %s synced to CRM (crm id: %s)", lead.reference, result.crm_lead_id)
            return lead

        lead.crm_sync_status = "pending"
        lead.crm_error = result.error
        db.commit()
        if delay > 0:
            time.sleep(delay)
            delay *= 2  # exponential backoff

    lead.crm_sync_status = "failed"
    db.commit()
    logger.warning("Lead %s failed CRM sync after %d attempt(s)", lead.reference, lead.crm_attempts)
    return lead


def sync_lead_by_id(
    lead_id: str,
    session_factory: sessionmaker,
    client: CRMClient,
    settings: Settings,
) -> None:
    """Entry point used by the background task after a public submission."""
    db: Session = session_factory()
    try:
        lead = db.get(Lead, lead_id)
        if lead is None or lead.status == "spam":
            return
        sync_lead(
            db,
            lead,
            client,
            max_attempts=settings.crm_max_attempts,
            backoff_seconds=settings.crm_retry_backoff_seconds,
        )
    except Exception:
        # The lead is safely stored; a later retry (manual or bulk) can recover.
        logger.exception("Unexpected error while syncing lead id=%s", lead_id)
        db.rollback()
    finally:
        db.close()


def retry_pending(db: Session, client: CRMClient, settings: Settings) -> dict:
    """Re-attempt synchronization for every pending/failed lead."""
    from ..crud import leads_pending_sync

    leads = leads_pending_sync(db)
    synced = failed = 0
    for lead in leads:
        sync_lead(
            db,
            lead,
            client,
            max_attempts=settings.crm_max_attempts,
            backoff_seconds=settings.crm_retry_backoff_seconds,
        )
        if lead.crm_sync_status == "synced":
            synced += 1
        else:
            failed += 1
    return {"processed": len(leads), "synced": synced, "failed": failed}
