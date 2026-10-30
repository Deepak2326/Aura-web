"""Pydantic schemas — server-side validation and sanitization boundaries.

LeadCreate mirrors the AURA CRM 'Machine Identifier' entity exactly:
Customer Name, Customer Segment, Total Revenue, Purchase Frequency,
Customer Value (+ CRM Status, which the server initializes to the first
pipeline stage rather than accepting from the client).
"""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .security import sanitize_text

_SINGLE_LINE_FIELDS = ("customer_name", "customer_segment", "source")


class LeadCreate(BaseModel):
    """Public lead-submission payload. `fax` is a hidden honeypot field."""

    model_config = ConfigDict(str_strip_whitespace=True, extra="ignore")

    # --- CRM entity fields (Machine Identifier) ---
    customer_name: str = Field(min_length=2, max_length=160)
    customer_segment: str = Field(min_length=2, max_length=80)
    total_revenue: float = Field(ge=0, le=1_000_000_000_000)
    purchase_frequency: int = Field(ge=0, le=1_000_000)
    customer_value: float = Field(ge=0, le=1_000_000_000_000)

    # --- Consent (stored locally only) ---
    consent_privacy: bool
    consent_contact: bool
    consent_marketing: bool = False

    # --- Metadata / abuse protection ---
    source: str = Field(default="Website", max_length=60)
    submission_id: str | None = Field(default=None, max_length=64)
    fax: str = Field(default="", max_length=120)  # honeypot — must stay empty

    @field_validator(*_SINGLE_LINE_FIELDS, mode="before")
    @classmethod
    def _clean_single_line(cls, value):
        return sanitize_text(value) if isinstance(value, str) else value

    @field_validator("consent_privacy")
    @classmethod
    def _privacy_required(cls, value: bool) -> bool:
        if value is not True:
            raise ValueError("You must accept the privacy policy.")
        return value

    @field_validator("consent_contact")
    @classmethod
    def _contact_required(cls, value: bool) -> bool:
        if value is not True:
            raise ValueError("You must agree to be contacted.")
        return value


class LeadSubmitResponse(BaseModel):
    reference: str
    status: str
    crm_sync_status: str
    message: str


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------
class LoginRequest(BaseModel):
    email: str = Field(max_length=254)
    password: str = Field(min_length=1, max_length=200)

    @field_validator("email")
    @classmethod
    def _lower(cls, value: str) -> str:
        return value.lower().strip()


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    email: str
    role: str


class AdminUserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    email: str
    role: str


# ---------------------------------------------------------------------------
# Admin / lead output
# ---------------------------------------------------------------------------
class SyncLogOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    attempt: int
    success: bool
    status_code: int | None
    error: str | None
    created_at: datetime


class LeadOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    reference: str
    customer_name: str
    customer_segment: str
    total_revenue: float
    purchase_frequency: int
    customer_value: float
    crm_status: str
    consent_privacy: bool
    consent_contact: bool
    consent_marketing: bool
    source: str
    status: str
    crm_sync_status: str
    crm_lead_id: str | None
    crm_error: str | None
    crm_attempts: int
    submitted_at: datetime
    updated_at: datetime


class LeadDetailOut(LeadOut):
    sync_logs: list[SyncLogOut] = []


class LeadListResponse(BaseModel):
    items: list[LeadOut]
    total: int
    page: int
    page_size: int


class StatsOut(BaseModel):
    total_leads: int
    synced: int
    pending: int
    failed: int
    spam: int
    today: int


class RetryResultOut(BaseModel):
    lead_id: str
    reference: str
    crm_sync_status: str
    crm_lead_id: str | None
    message: str


class RetryPendingOut(BaseModel):
    processed: int
    synced: int
    failed: int
