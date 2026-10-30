"""Mock CRM provider for local development and automated tests.

Deterministic behaviours:
  - "success":   every call succeeds, returns a MOCK-* lead id.
  - "fail":      every call fails (simulates CRM outage).
  - "fail_once": the first call fails, subsequent calls succeed (retry path).
"""
from __future__ import annotations

import uuid

from .base import CRMClient, CRMResult


class MockCRMClient(CRMClient):
    name = "mock"

    def __init__(self, behavior: str = "success", field_mapping: dict[str, str] | None = None):
        super().__init__(field_mapping)
        if behavior not in {"success", "fail", "fail_once"}:
            raise ValueError(f"Unknown mock behavior: {behavior}")
        self.behavior = behavior
        self.calls: list[dict] = []

    def create_lead(self, payload: dict) -> CRMResult:
        self.calls.append(payload)
        if self.behavior == "fail" or (self.behavior == "fail_once" and len(self.calls) == 1):
            return CRMResult(success=False, status_code=503, error="mock_crm_unavailable")
        return CRMResult(success=True, crm_lead_id=f"MOCK-{uuid.uuid4().hex[:12].upper()}", status_code=201)
