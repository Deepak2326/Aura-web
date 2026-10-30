"""Public lead-capture endpoints."""
from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from .. import crud
from ..deps import get_db
from ..rate_limit import client_ip, enforce_rate_limit
from ..schemas import LeadCreate, LeadSubmitResponse
from ..security import hash_ip
from ..services.sync import sync_lead_by_id

router = APIRouter(prefix="/api", tags=["leads"])


@router.post("/leads", status_code=201, response_model=LeadSubmitResponse)
def submit_lead(
    payload: LeadCreate,
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
) -> LeadSubmitResponse:
    enforce_rate_limit(request, "submit_limiter")
    settings = request.app.state.settings

    # Idempotency: a retried submission (same client-generated id) returns the
    # original lead instead of creating a duplicate.
    if payload.submission_id:
        existing = crud.get_by_submission_id(db, payload.submission_id)
        if existing is not None:
            return LeadSubmitResponse(
                reference=existing.reference,
                status=existing.status,
                crm_sync_status=existing.crm_sync_status,
                message="Your inquiry was already received. Our team will reach out shortly.",
            )

    is_spam = bool(payload.fax.strip())  # honeypot filled => bot

    if not is_spam:
        duplicate = crud.find_duplicate(
            db, customer_name=payload.customer_name, window_hours=settings.duplicate_window_hours
        )
        if duplicate is not None:
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "DUPLICATE_LEAD",
                    "message": "We have already received a registration for this customer name recently. "
                    "Our team will contact you soon.",
                    "reference": duplicate.reference,
                },
            )

    lead = crud.create_lead(
        db,
        payload,
        status="spam" if is_spam else "new",
        ip_hash=hash_ip(client_ip(request)),
    )

    # CRM sync runs after the response so a slow/down CRM never blocks the user.
    # Failures are retried automatically; the lead is safely stored either way.
    if not is_spam:
        background_tasks.add_task(
            sync_lead_by_id,
            lead.id,
            request.app.state.session_factory,
            request.app.state.crm_client,
            settings,
        )

    return LeadSubmitResponse(
        reference=lead.reference,
        status=lead.status,
        crm_sync_status=lead.crm_sync_status,
        message="Thank you! Your details have been received. Our team will contact you shortly.",
    )
