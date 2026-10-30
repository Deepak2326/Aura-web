"""Provider for the user's existing AURA Self-Evolving CRM.

Connection details are 100% environment-driven — the exact create-record
endpoint, auth header and any extra static payload fields (e.g. workspace /
entity identifiers) come from AURA_CRM_* variables, captured via
docs/CRM_MAPPING_WORKSHEET.md. No endpoint paths are hardcoded or fabricated.
"""
from __future__ import annotations

import httpx

from .generic_rest import GenericRESTCRMClient


class AuraCRMClient(GenericRESTCRMClient):
    name = "aura_crm"

    def __init__(
        self,
        *,
        api_url: str,
        api_key: str = "",
        auth_header: str = "Authorization",
        auth_scheme: str = "Bearer",
        extra_payload: dict | None = None,
        timeout: float = 10.0,
        response_id_path: str = "id",
        field_mapping: dict[str, str] | None = None,
        transport: httpx.BaseTransport | None = None,  # injectable for tests
    ):
        super().__init__(
            base_url=api_url,
            api_key="",  # auth header is built below — supports any header name/scheme
            timeout=timeout,
            response_id_path=response_id_path,
            field_mapping=field_mapping,
            transport=transport,
        )
        self.api_key = api_key
        self.auth_header = auth_header
        self.auth_scheme = auth_scheme
        self.extra_payload = extra_payload or {}

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        if self.api_key:
            headers[self.auth_header] = f"{self.auth_scheme} {self.api_key}".strip()
        return headers

    def create_lead(self, payload: dict):
        # Merge static fields the AURA API may require (workspace, entity…).
        return super().create_lead({**payload, **self.extra_payload})
