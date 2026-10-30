"""Unit tests for schema-level validation and sanitization.

LeadCreate mirrors the AURA CRM 'Machine Identifier' entity:
Customer Name, Customer Segment, Total Revenue, Purchase Frequency,
Customer Value (+ server-set CRM Status).
"""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.schemas import LeadCreate
from tests.conftest import make_lead_payload


def test_valid_payload_passes():
    lead = LeadCreate(**make_lead_payload())
    assert lead.customer_name.startswith("Customer ")
    assert lead.source == "Website"


def test_customer_name_too_short_rejected():
    with pytest.raises(ValidationError):
        LeadCreate(**make_lead_payload(customer_name="A"))


def test_customer_segment_required():
    with pytest.raises(ValidationError):
        LeadCreate(**make_lead_payload(customer_segment=""))


def test_negative_total_revenue_rejected():
    with pytest.raises(ValidationError):
        LeadCreate(**make_lead_payload(total_revenue=-100))


def test_negative_customer_value_rejected():
    with pytest.raises(ValidationError):
        LeadCreate(**make_lead_payload(customer_value=-1))


def test_fractional_purchase_frequency_rejected():
    with pytest.raises(ValidationError):
        LeadCreate(**make_lead_payload(purchase_frequency=5.5))


def test_non_numeric_purchase_frequency_rejected():
    with pytest.raises(ValidationError):
        LeadCreate(**make_lead_payload(purchase_frequency="many"))


def test_html_is_stripped_from_text_fields():
    lead = LeadCreate(**make_lead_payload(customer_name="<script>alert(1)</script>Acme Corp"))
    assert "<" not in lead.customer_name and ">" not in lead.customer_name
    assert "Acme Corp" in lead.customer_name


def test_privacy_consent_must_be_true():
    with pytest.raises(ValidationError):
        LeadCreate(**make_lead_payload(consent_privacy=False))


def test_contact_consent_must_be_true():
    with pytest.raises(ValidationError):
        LeadCreate(**make_lead_payload(consent_contact=False))


def test_source_defaults_to_website():
    payload = make_lead_payload()
    payload.pop("source")
    lead = LeadCreate(**payload)
    assert lead.source == "Website"


def test_crm_status_is_not_client_settable():
    """The pipeline stage is assigned server-side; client input is ignored."""
    lead = LeadCreate(**make_lead_payload(crm_status="High Value"))
    assert not hasattr(lead, "crm_status")  # extra fields are ignored by the schema


def test_required_fields_enforced():
    payload = make_lead_payload()
    del payload["customer_name"]
    with pytest.raises(ValidationError):
        LeadCreate(**payload)
