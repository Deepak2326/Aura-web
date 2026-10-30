"""CRM provider factory — selects the client based on configuration."""
from __future__ import annotations

from ..config import Settings
from .aura_crm import AuraCRMClient
from .base import CRMClient, NullCRMClient
from .generic_rest import GenericRESTCRMClient
from .mock import MockCRMClient


def build_crm_client(settings: Settings) -> CRMClient:
    provider = settings.crm_provider.strip().lower()
    mapping = settings.field_mapping()

    if provider == "aura_crm":
        if not settings.aura_crm_api_url:
            raise ValueError("AURA_CRM_API_URL must be set when CRM_PROVIDER=aura_crm")
        return AuraCRMClient(
            api_url=settings.aura_crm_api_url,
            api_key=settings.aura_crm_api_key,
            auth_header=settings.aura_crm_auth_header,
            auth_scheme=settings.aura_crm_auth_scheme,
            extra_payload=settings.aura_crm_extra_payload_dict(),
            timeout=settings.crm_timeout_seconds,
            response_id_path=settings.crm_response_id_path,
            field_mapping=mapping,
        )
    if provider == "mock":
        return MockCRMClient(behavior=settings.crm_mock_behavior, field_mapping=mapping)
    if provider == "generic_rest":
        if not settings.crm_api_url:
            raise ValueError("CRM_API_URL must be set when CRM_PROVIDER=generic_rest")
        return GenericRESTCRMClient(
            base_url=settings.crm_api_url,
            api_key=settings.crm_api_key,
            timeout=settings.crm_timeout_seconds,
            response_id_path=settings.crm_response_id_path,
            field_mapping=mapping,
        )
    if provider == "none":
        return NullCRMClient(field_mapping=mapping)
    raise ValueError(
        f"Unknown CRM provider: {settings.crm_provider!r} (expected aura_crm | mock | generic_rest | none)"
    )
