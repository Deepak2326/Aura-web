"""Tests for the CRM integration layer and the sync/retry machinery.

The generic REST provider is tested with an httpx MockTransport — no real
external CRM endpoint is contacted or fabricated.
"""
from __future__ import annotations

import httpx

from app import crud
from app.crm import AuraCRMClient, GenericRESTCRMClient, MockCRMClient
from app.crm.base import DEFAULT_FIELD_MAPPING
from app.services.sync import serialize_lead, sync_lead
from app.models import Lead, SyncLog
from app.schemas import LeadCreate
from tests.conftest import make_lead_payload


def _get_first_lead(app) -> Lead:
    db = app.state.session_factory()
    try:
        return db.query(Lead).first()
    finally:
        db.close()


def test_mock_success_marks_lead_synced(client, app):
    client.post("/api/leads", json=make_lead_payload())
    lead = _get_first_lead(app)
    assert lead.crm_sync_status == "synced"
    assert lead.crm_lead_id.startswith("MOCK-")
    assert lead.crm_attempts == 1


def test_crm_outage_marks_failed_without_losing_lead(client, app, auth_headers):
    app.state.crm_client = MockCRMClient(behavior="fail")
    response = client.post("/api/leads", json=make_lead_payload())
    assert response.status_code == 201  # user is unaffected by the outage

    lead = _get_first_lead(app)
    assert lead.crm_sync_status == "failed"
    assert lead.crm_attempts == 3  # configured max attempts
    assert lead.crm_error == "mock_crm_unavailable"

    db = app.state.session_factory()
    try:
        assert db.query(SyncLog).count() == 3
    finally:
        db.close()

    # CRM "recovers" → manual retry succeeds.
    app.state.crm_client = MockCRMClient(behavior="success")
    retry = client.post(f"/api/admin/leads/{lead.id}/retry-sync", headers=auth_headers)
    assert retry.status_code == 200
    assert retry.json()["crm_sync_status"] == "synced"
    assert _get_first_lead(app).crm_lead_id.startswith("MOCK-")


def test_fail_once_then_success_via_backoff_retry(client, app):
    app.state.crm_client = MockCRMClient(behavior="fail_once")
    client.post("/api/leads", json=make_lead_payload())
    lead = _get_first_lead(app)
    assert lead.crm_sync_status == "synced"
    assert lead.crm_attempts == 2


def test_retry_pending_bulk_endpoint(client, app, auth_headers):
    app.state.crm_client = MockCRMClient(behavior="fail")
    client.post("/api/leads", json=make_lead_payload())
    client.post("/api/leads", json=make_lead_payload())

    app.state.crm_client = MockCRMClient(behavior="success")
    result = client.post("/api/admin/sync/retry-pending", headers=auth_headers)
    assert result.status_code == 200
    assert result.json() == {"processed": 2, "synced": 2, "failed": 0}


def test_spam_leads_are_not_retried(client, app, auth_headers):
    client.post("/api/leads", json=make_lead_payload(fax="bot-filled"))
    result = client.post("/api/admin/sync/retry-pending", headers=auth_headers)
    assert result.json()["processed"] == 0


def test_field_mapping_transform():
    client = MockCRMClient(field_mapping={"Customer Name": "customer_name", "Total Revenue": "total_revenue"})
    payload = client.build_payload({"customer_name": "Acme", "total_revenue": 100.0, "customer_value": 5.0})
    assert payload == {"Customer Name": "Acme", "Total Revenue": 100.0}


def test_default_mapping_covers_all_crm_entity_fields():
    """Every 'Machine Identifier' dynamic field + source must be mapped."""
    for internal in (
        "customer_name", "customer_segment", "total_revenue",
        "purchase_frequency", "customer_value", "crm_status", "source",
    ):
        assert internal in DEFAULT_FIELD_MAPPING.values()


def test_serialize_lead_produces_json_safe_data(client, app):
    client.post("/api/leads", json=make_lead_payload())
    lead = _get_first_lead(app)
    data = serialize_lead(lead)
    assert isinstance(data["submitted_at"], str)
    assert isinstance(data["consent_privacy"], bool)
    assert isinstance(data["total_revenue"], float)


def test_generic_rest_success_parses_nested_id():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["Authorization"] == "Bearer secret-key"
        return httpx.Response(201, json={"data": {"id": "CRM-777"}})

    client = GenericRESTCRMClient(
        base_url="https://crm.invalid/api/leads",
        api_key="secret-key",
        response_id_path="data.id",
        transport=httpx.MockTransport(handler),
    )
    result = client.create_lead({"Name": "Priya"})
    assert result.success is True
    assert result.crm_lead_id == "CRM-777"
    assert result.status_code == 201


def test_generic_rest_http_error_is_failure():
    client = GenericRESTCRMClient(
        base_url="https://crm.invalid/api/leads",
        transport=httpx.MockTransport(lambda request: httpx.Response(500, json={"error": "boom"})),
    )
    result = client.create_lead({})
    assert result.success is False
    assert result.status_code == 500
    assert result.error == "crm_http_500"


def test_generic_rest_connection_error_is_failure():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused")

    client = GenericRESTCRMClient(
        base_url="https://crm.invalid/api/leads",
        transport=httpx.MockTransport(handler),
    )
    result = client.create_lead({})
    assert result.success is False
    assert result.error.startswith("connection_error:")


def test_sync_lead_disabled_provider_marks_disabled(client, app, settings):
    # `client` fixture ensures app lifespan ran (tables created).
    from app.crm.base import NullCRMClient

    db = app.state.session_factory()
    try:
        lead = crud.create_lead(db, payload=LeadCreate(**make_lead_payload()), status="new", ip_hash=None)
        sync_lead(db, lead, NullCRMClient(), max_attempts=1, backoff_seconds=0)
        assert lead.crm_sync_status == "disabled"
    finally:
        db.close()


def test_aura_crm_client_merges_extra_payload_and_custom_auth_header():
    """The AURA provider posts the mapped payload + static fields with the
    configured auth header — verified against an httpx mock, no live calls."""
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        import json

        captured["auth"] = request.headers.get("x-api-key")
        captured["body"] = json.loads(request.content)
        return httpx.Response(201, json={"record_id": "REC-42"})

    client = AuraCRMClient(
        api_url="https://aura.invalid/api/records",
        api_key="secret-token",
        auth_header="x-api-key",
        auth_scheme="",
        extra_payload={"entity": "machine_identifier", "workspace": "Analytical_E_Commerce_CRM"},
        response_id_path="record_id",
        transport=httpx.MockTransport(handler),
    )
    result = client.create_lead({"Customer Name": "Acme", "CRM Status": "New"})

    assert result.success is True
    assert result.crm_lead_id == "REC-42"
    assert captured["auth"] == "secret-token"
    assert captured["body"]["Customer Name"] == "Acme"
    assert captured["body"]["entity"] == "machine_identifier"
    assert captured["body"]["workspace"] == "Analytical_E_Commerce_CRM"


def test_aura_crm_client_bearer_scheme():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["Authorization"] == "Bearer tok123"
        return httpx.Response(200, json={"id": "R1"})

    client = AuraCRMClient(
        api_url="https://aura.invalid/api/records",
        api_key="tok123",
        transport=httpx.MockTransport(handler),
    )
    assert client.create_lead({}).success is True
