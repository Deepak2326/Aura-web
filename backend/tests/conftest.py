"""Shared test fixtures.

Each test run gets an isolated app instance with its own temporary SQLite
database, deterministic settings and the mock CRM provider.
"""
from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


@pytest.fixture()
def settings(tmp_path) -> Settings:
    return Settings(
        environment="test",
        database_url=f"sqlite:///{tmp_path / 'test.db'}",
        jwt_secret="test-secret-key",
        jwt_expire_minutes=60,
        admin_default_email="admin@test.dev",
        admin_default_password="AdminPass!123",
        crm_provider="mock",
        crm_mock_behavior="success",
        crm_retry_backoff_seconds=0.0,
        crm_max_attempts=3,
        rate_limit_submit_max=1000,
        rate_limit_login_max=1000,
        duplicate_window_hours=24,
        db_auto_create=True,
    )


@pytest.fixture()
def app(settings):
    return create_app(settings)


@pytest.fixture()
def client(app):
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture()
def admin_token(client) -> str:
    response = client.post(
        "/api/auth/login",
        json={"email": "admin@test.dev", "password": "AdminPass!123"},
    )
    assert response.status_code == 200, response.text
    return response.json()["access_token"]


@pytest.fixture()
def auth_headers(admin_token) -> dict:
    return {"Authorization": f"Bearer {admin_token}"}


def make_lead_payload(**overrides) -> dict:
    """A fully valid payload (unique customer name) mirroring the CRM entity."""
    payload = {
        "customer_name": f"Customer {uuid.uuid4().hex[:6]}",
        "customer_segment": "Wholesale",
        "total_revenue": 50000,
        "purchase_frequency": 5,
        "customer_value": 10000,
        "consent_privacy": True,
        "consent_contact": True,
        "consent_marketing": False,
        "source": "Website",
    }
    payload.update(overrides)
    return payload


@pytest.fixture()
def lead_payload() -> dict:
    return make_lead_payload()
