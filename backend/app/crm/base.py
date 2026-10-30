"""CRM client abstraction and configurable field mapping.

Every CRM provider implements `create_lead(payload)`. The payload is produced
by `build_payload`, which maps internal lead fields to CRM-specific field
names using a configurable mapping (env: CRM_FIELD_MAPPING).
"""
from __future__ import annotations

from abc import ABC, abstractmethod

from pydantic import BaseModel

# Default mapping: AURA CRM field label -> internal lead attribute.
# Mirrors the 'Machine Identifier' entity of the Analytical_E_Commerce_CRM
# workspace (see docs/CRM_MAPPING_WORKSHEET.md). Override via the
# CRM_FIELD_MAPPING environment variable (JSON object) once the real
# create-record request is captured and the exact payload keys are confirmed.
DEFAULT_FIELD_MAPPING: dict[str, str] = {
    "Customer Name": "customer_name",
    "Customer Segment": "customer_segment",
    "Total Revenue": "total_revenue",
    "Purchase Frequency": "purchase_frequency",
    "Customer Value": "customer_value",
    "CRM Status": "crm_status",
    "Source": "source",
    # Unique website reference — lets the AURA endpoint dedupe/idempotently
    # accept retried submissions (see docs/AURA_API_CONTRACT.md).
    "External Reference": "reference",
}


class CRMResult(BaseModel):
    success: bool
    crm_lead_id: str | None = None
    status_code: int | None = None
    error: str | None = None


class CRMClient(ABC):
    """Base class for CRM providers."""

    name: str = "base"

    def __init__(self, field_mapping: dict[str, str] | None = None):
        self.field_mapping = field_mapping or DEFAULT_FIELD_MAPPING

    def build_payload(self, lead_data: dict) -> dict:
        """Transform internal lead data into the CRM's field format."""
        payload = {}
        for crm_field, source_field in self.field_mapping.items():
            value = lead_data.get(source_field)
            if value is not None:
                payload[crm_field] = value
        return payload

    @abstractmethod
    def create_lead(self, payload: dict) -> CRMResult:
        """Send a lead to the CRM. Must never raise — return CRMResult instead."""
        raise NotImplementedError


class NullCRMClient(CRMClient):
    """Used when CRM_PROVIDER=none — synchronization is disabled."""

    name = "null"

    def create_lead(self, payload: dict) -> CRMResult:  # pragma: no cover - trivial
        return CRMResult(success=True, crm_lead_id=None, status_code=None)
