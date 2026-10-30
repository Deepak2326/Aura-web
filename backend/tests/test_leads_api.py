"""API tests for the public lead-capture endpoint."""
from __future__ import annotations

from app.rate_limit import SlidingWindowRateLimiter
from tests.conftest import make_lead_payload


def test_submit_lead_success(client, lead_payload, auth_headers):
    response = client.post("/api/leads", json=lead_payload)
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["reference"].startswith("AUR-")
    assert body["status"] == "new"

    # Background CRM sync should have completed with the mock provider.
    listing = client.get("/api/admin/leads", headers=auth_headers).json()
    assert listing["total"] == 1
    item = listing["items"][0]
    assert item["crm_sync_status"] == "synced"
    assert item["crm_lead_id"].startswith("MOCK-")
    assert item["customer_name"] == lead_payload["customer_name"]
    assert item["crm_status"] == "New"  # initial pipeline stage


def test_invalid_revenue_returns_422(client, lead_payload):
    lead_payload["total_revenue"] = -500
    response = client.post("/api/leads", json=lead_payload)
    assert response.status_code == 422


def test_missing_consent_returns_422(client, lead_payload):
    lead_payload["consent_privacy"] = False
    response = client.post("/api/leads", json=lead_payload)
    assert response.status_code == 422


def test_duplicate_customer_name_rejected_within_window(client, lead_payload):
    first = client.post("/api/leads", json=lead_payload)
    assert first.status_code == 201

    second = client.post("/api/leads", json=lead_payload)
    assert second.status_code == 409
    detail = second.json()["detail"]
    assert detail["code"] == "DUPLICATE_LEAD"
    assert detail["reference"].startswith("AUR-")


def test_same_customer_allowed_after_window_expires(client, lead_payload, settings):
    settings.duplicate_window_hours = 0  # simulate expired window
    assert client.post("/api/leads", json=lead_payload).status_code == 201
    assert client.post("/api/leads", json=lead_payload).status_code == 201


def test_honeypot_marks_spam_and_skips_crm(client, lead_payload, auth_headers):
    lead_payload["fax"] = "555-0100"  # only bots see/fill this field
    response = client.post("/api/leads", json=lead_payload)
    assert response.status_code == 201  # bots get a plausible success

    listing = client.get("/api/admin/leads?status=spam", headers=auth_headers).json()
    assert listing["total"] == 1
    assert listing["items"][0]["crm_sync_status"] == "skipped"


def test_idempotent_submission_returns_same_lead(client, lead_payload):
    lead_payload["submission_id"] = "client-generated-uuid-1234"
    first = client.post("/api/leads", json=lead_payload)
    second = client.post("/api/leads", json=lead_payload)
    assert first.status_code == 201 and second.status_code == 201
    assert first.json()["reference"] == second.json()["reference"]


def test_rate_limit_returns_429(client, app, lead_payload):
    app.state.submit_limiter = SlidingWindowRateLimiter(max_requests=2, window_seconds=60)
    assert client.post("/api/leads", json=lead_payload).status_code == 201
    assert client.post("/api/leads", json=make_lead_payload()).status_code == 201
    blocked = client.post("/api/leads", json=make_lead_payload())
    assert blocked.status_code == 429
    assert blocked.json()["detail"]["code"] == "RATE_LIMITED"


def test_health_endpoint(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
