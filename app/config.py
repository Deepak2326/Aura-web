"""Application configuration loaded from environment variables / .env file.

Never hardcode secrets here — everything is environment-driven so the same
code runs in development (SQLite + mock CRM) and production (PostgreSQL +
real CRM) by only changing the environment.
"""
from __future__ import annotations

import json
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # --- Core ---
    app_name: str = "Aura Lead Capture API"
    environment: str = "development"
    database_url: str = "sqlite:///./aura_leads.db"
    # Auto-create tables on startup (handy for SQLite dev). In production use
    # Alembic migrations instead and set this to false.
    db_auto_create: bool = True
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    # --- Auth / Admin ---
    jwt_secret: str = "dev-only-insecure-secret-change-me"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 720
    admin_default_email: str = "admin@example.com"
    admin_default_password: str = "ChangeMe!123"

    # --- Abuse protection ---
    rate_limit_submit_max: int = 5
    rate_limit_submit_window: int = 600  # seconds
    rate_limit_login_max: int = 10
    rate_limit_login_window: int = 600  # seconds
    duplicate_window_hours: int = 24

    # --- CRM integration ---
    crm_provider: str = "mock"  # aura_crm | mock | generic_rest | none
    crm_mock_behavior: str = "success"  # success | fail | fail_once
    crm_api_url: str = ""
    crm_api_key: str = ""
    crm_timeout_seconds: float = 10.0
    crm_response_id_path: str = "id"  # dotted path in CRM JSON response, e.g. "data.id"
    crm_max_attempts: int = 3
    crm_retry_backoff_seconds: float = 1.0
    crm_field_mapping: str = ""  # optional JSON object: {"CrmField": "lead_field"}

    # --- AURA Self-Evolving CRM (the user's existing CRM) ---
    # Values come from the captured create-record request — see
    # docs/CRM_MAPPING_WORKSHEET.md. Nothing is hardcoded.
    aura_crm_api_url: str = ""
    aura_crm_api_key: str = ""
    aura_crm_auth_header: str = "Authorization"
    aura_crm_auth_scheme: str = "Bearer"
    aura_crm_extra_payload: str = ""  # optional JSON merged into every create request

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    def field_mapping(self) -> dict[str, str] | None:
        """Return the user-configured CRM field mapping, or None to use defaults."""
        raw = self.crm_field_mapping.strip()
        if not raw:
            return None
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:  # fail fast on bad config
            raise ValueError(f"CRM_FIELD_MAPPING is not valid JSON: {exc}") from exc
        if not isinstance(data, dict) or not all(isinstance(k, str) and isinstance(v, str) for k, v in data.items()):
            raise ValueError("CRM_FIELD_MAPPING must be a JSON object of string:string pairs")
        return data

    def aura_crm_extra_payload_dict(self) -> dict:
        """Static fields merged into every AURA create-record request (e.g. workspace/entity)."""
        raw = self.aura_crm_extra_payload.strip()
        if not raw:
            return {}
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValueError(f"AURA_CRM_EXTRA_PAYLOAD is not valid JSON: {exc}") from exc
        if not isinstance(data, dict):
            raise ValueError("AURA_CRM_EXTRA_PAYLOAD must be a JSON object")
        return data


@lru_cache
def get_settings() -> Settings:
    return Settings()
