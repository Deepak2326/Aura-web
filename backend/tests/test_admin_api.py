"""API tests for authentication and the protected admin dashboard endpoints."""
from __future__ import annotations

from app import crud
from tests.conftest import make_lead_payload


def _login(client, email: str, password: str) -> str:
    response = client.post("/api/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200, response.text
    return response.json()["access_token"]


def test_admin_endpoints_require_auth(client):
    assert client.get("/api/admin/stats").status_code == 401
    assert client.get("/api/admin/leads").status_code == 401
    assert client.get("/api/admin/leads/export.csv").status_code == 401


def test_login_with_wrong_password_rejected(client):
    response = client.post(
        "/api/auth/login",
        json={"email": "admin@test.dev", "password": "wrong-password"},
    )
    assert response.status_code == 401
    assert response.json()["detail"]["code"] == "INVALID_CREDENTIALS"


def test_invalid_token_rejected(client):
    response = client.get("/api/admin/stats", headers={"Authorization": "Bearer not-a-token"})
    assert response.status_code == 401


def test_stats_counts(client, auth_headers):
    client.post("/api/leads", json=make_lead_payload())
    client.post("/api/leads", json=make_lead_payload())
    stats = client.get("/api/admin/stats", headers=auth_headers).json()
    assert stats["total_leads"] == 2
    assert stats["synced"] == 2
    assert stats["pending"] == 0
    assert stats["failed"] == 0
    assert stats["today"] == 2


def test_search_and_filters(client, auth_headers):
    client.post("/api/leads", json=make_lead_payload(customer_name="Zeta Widgets"))
    client.post("/api/leads", json=make_lead_payload(customer_name="Omega Foods"))

    result = client.get("/api/admin/leads?q=zeta", headers=auth_headers).json()
    assert result["total"] == 1
    assert result["items"][0]["customer_name"] == "Zeta Widgets"

    result = client.get("/api/admin/leads?sync_status=synced", headers=auth_headers).json()
    assert result["total"] == 2
    result = client.get("/api/admin/leads?sync_status=failed", headers=auth_headers).json()
    assert result["total"] == 0


def test_pipeline_stage_filter(client, auth_headers):
    client.post("/api/leads", json=make_lead_payload())
    result = client.get("/api/admin/leads?stage=New", headers=auth_headers).json()
    assert result["total"] == 1
    result = client.get("/api/admin/leads?stage=High%20Value", headers=auth_headers).json()
    assert result["total"] == 0


def test_date_filter(client, auth_headers):
    client.post("/api/leads", json=make_lead_payload())
    result = client.get("/api/admin/leads?date_from=2000-01-01&date_to=2000-01-02", headers=auth_headers)
    assert result.json()["total"] == 0
    result = client.get("/api/admin/leads?date_from=2000-01-01", headers=auth_headers)
    assert result.json()["total"] == 1


def test_pagination(client, auth_headers):
    for _ in range(3):
        client.post("/api/leads", json=make_lead_payload())
    page1 = client.get("/api/admin/leads?page=1&page_size=2", headers=auth_headers).json()
    assert page1["total"] == 3 and len(page1["items"]) == 2
    page2 = client.get("/api/admin/leads?page=2&page_size=2", headers=auth_headers).json()
    assert len(page2["items"]) == 1


def test_lead_detail_includes_sync_logs(client, auth_headers):
    client.post("/api/leads", json=make_lead_payload())
    item = client.get("/api/admin/leads", headers=auth_headers).json()["items"][0]
    detail = client.get(f"/api/admin/leads/{item['id']}", headers=auth_headers).json()
    assert detail["reference"] == item["reference"]
    assert len(detail["sync_logs"]) == 1
    assert detail["sync_logs"][0]["success"] is True


def test_missing_lead_returns_404(client, auth_headers):
    response = client.get("/api/admin/leads/does-not-exist", headers=auth_headers)
    assert response.status_code == 404


def test_csv_export(client, auth_headers):
    client.post("/api/leads", json=make_lead_payload(customer_name="Export Person"))
    response = client.get("/api/admin/leads/export.csv", headers=auth_headers)
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    lines = response.text.strip().splitlines()
    assert lines[0].startswith("reference,submitted_at,customer_name")
    assert "Export Person" in lines[1]


def test_viewer_role_cannot_retry_sync(client, app, auth_headers):
    db = app.state.session_factory()
    try:
        crud.create_admin(db, email="viewer@test.dev", password="ViewerPass!123", role="viewer")
    finally:
        db.close()
    viewer_token = _login(client, "viewer@test.dev", "ViewerPass!123")
    viewer_headers = {"Authorization": f"Bearer {viewer_token}"}

    # Viewer can read…
    assert client.get("/api/admin/stats", headers=viewer_headers).status_code == 200
    # …but cannot trigger synchronization.
    client.post("/api/leads", json=make_lead_payload())
    lead_id = client.get("/api/admin/leads", headers=auth_headers).json()["items"][0]["id"]
    response = client.post(f"/api/admin/leads/{lead_id}/retry-sync", headers=viewer_headers)
    assert response.status_code == 403
    assert client.post("/api/admin/sync/retry-pending", headers=viewer_headers).status_code == 403
