"""Protected admin endpoints: stats, lead listing/filtering, export, CRM retry."""
from __future__ import annotations

import csv
import io
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from .. import crud
from ..deps import get_current_admin, get_db, require_admin
from ..models import AdminUser, Lead
from ..schemas import (
    LeadDetailOut,
    LeadListResponse,
    RetryPendingOut,
    RetryResultOut,
    StatsOut,
)
from ..services.sync import retry_pending, sync_lead

router = APIRouter(prefix="/api/admin", tags=["admin"])

EXPORT_COLUMNS = [
    "reference", "submitted_at", "customer_name", "customer_segment",
    "total_revenue", "purchase_frequency", "customer_value", "crm_status",
    "source", "status", "crm_sync_status", "crm_lead_id", "crm_attempts",
    "consent_privacy", "consent_contact", "consent_marketing",
]


@router.get("/stats", response_model=StatsOut)
def get_stats(
    db: Session = Depends(get_db),
    _: AdminUser = Depends(get_current_admin),
) -> dict:
    return crud.stats(db)


def _parse_filters(
    q: str | None,
    status: str | None,
    stage: str | None,
    sync_status: str | None,
    date_from: date | None,
    date_to: date | None,
) -> dict:
    return {
        "q": q,
        "status": status,
        "stage": stage,
        "sync_status": sync_status,
        "date_from": date_from,
        "date_to": date_to,
    }


# NOTE: this route must be declared BEFORE /leads/{lead_id} so "export.csv"
# is not captured by the path parameter.
@router.get("/leads/export.csv")
def export_leads_csv(
    request: Request,
    q: str | None = None,
    status: str | None = None,
    stage: str | None = None,
    sync_status: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    db: Session = Depends(get_db),
    _: AdminUser = Depends(get_current_admin),
) -> StreamingResponse:
    filters = _parse_filters(q, status, stage, sync_status, date_from, date_to)
    leads, _ = crud.list_leads(db, **filters, page=1, page_size=10_000)

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(EXPORT_COLUMNS)
    for lead in leads:
        writer.writerow([getattr(lead, column) for column in EXPORT_COLUMNS])
    buffer.seek(0)

    return StreamingResponse(
        iter([buffer.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="leads-export.csv"'},
    )


@router.get("/leads", response_model=LeadListResponse)
def list_leads(
    q: str | None = None,
    status: str | None = None,
    stage: str | None = None,
    sync_status: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    _: AdminUser = Depends(get_current_admin),
) -> LeadListResponse:
    filters = _parse_filters(q, status, stage, sync_status, date_from, date_to)
    items, total = crud.list_leads(db, **filters, page=page, page_size=page_size)
    return LeadListResponse(items=items, total=total, page=page, page_size=page_size)


@router.get("/leads/{lead_id}", response_model=LeadDetailOut)
def get_lead(
    lead_id: str,
    db: Session = Depends(get_db),
    _: AdminUser = Depends(get_current_admin),
) -> Lead:
    lead = crud.get_lead(db, lead_id)
    if lead is None:
        raise HTTPException(status_code=404, detail={"code": "LEAD_NOT_FOUND", "message": "Lead not found."})
    return lead


@router.post("/leads/{lead_id}/retry-sync", response_model=RetryResultOut)
def retry_lead_sync(
    lead_id: str,
    request: Request,
    db: Session = Depends(get_db),
    _: AdminUser = Depends(require_admin),
) -> RetryResultOut:
    lead = crud.get_lead(db, lead_id)
    if lead is None:
        raise HTTPException(status_code=404, detail={"code": "LEAD_NOT_FOUND", "message": "Lead not found."})
    if lead.status == "spam":
        raise HTTPException(
            status_code=400,
            detail={"code": "NOT_RETRYABLE", "message": "Spam submissions are never sent to the CRM."},
        )
    settings = request.app.state.settings
    sync_lead(
        db,
        lead,
        request.app.state.crm_client,
        max_attempts=settings.crm_max_attempts,
        backoff_seconds=settings.crm_retry_backoff_seconds,
    )
    db.refresh(lead)
    return RetryResultOut(
        lead_id=lead.id,
        reference=lead.reference,
        crm_sync_status=lead.crm_sync_status,
        crm_lead_id=lead.crm_lead_id,
        message="Lead synchronized with the CRM." if lead.crm_sync_status == "synced"
        else "Synchronization failed again. It will remain queued for retry.",
    )


@router.post("/sync/retry-pending", response_model=RetryPendingOut)
def retry_all_pending(
    request: Request,
    db: Session = Depends(get_db),
    _: AdminUser = Depends(require_admin),
) -> dict:
    settings = request.app.state.settings
    return retry_pending(db, request.app.state.crm_client, settings)
