"""Generic REST CRM provider.

Configure with environment variables:
  CRM_PROVIDER=generic_rest
  CRM_API_URL=https://your-crm.example.com/api/leads
  CRM_API_KEY=<secret>            (sent as Bearer token; never in frontend code)
  CRM_RESPONSE_ID_PATH=data.id    (dotted path to the created lead id in the JSON response)
  CRM_FIELD_MAPPING={"Name": "full_name", ...}

This intentionally implements a plain "POST JSON, read id from response"
contract. Adapt `_headers`/`create_lead` when you wire up a concrete CRM —
the retry/audit machinery in services/sync.py works unchanged.
"""
from __future__ import annotations

import httpx

from .base import CRMClient, CRMResult


def _extract_path(data, path: str):
    current = data
    for part in path.split("."):
        if not isinstance(current, dict) or part not in current:
            return None
        current = current[part]
    return current


class GenericRESTCRMClient(CRMClient):
    name = "generic_rest"

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str = "",
        timeout: float = 10.0,
        response_id_path: str = "id",
        field_mapping: dict[str, str] | None = None,
        transport: httpx.BaseTransport | None = None,  # injectable for tests
    ):
        super().__init__(field_mapping)
        self.base_url = base_url
        self.api_key = api_key
        self.timeout = timeout
        self.response_id_path = response_id_path
        self._transport = transport

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    def create_lead(self, payload: dict) -> CRMResult:
        try:
            with httpx.Client(timeout=self.timeout, transport=self._transport) as client:
                response = client.post(self.base_url, json=payload, headers=self._headers())
        except httpx.HTTPError as exc:
            # Do not leak internals (URLs, headers) into stored errors.
            return CRMResult(success=False, error=f"connection_error:{type(exc).__name__}")

        if 200 <= response.status_code < 300:
            crm_id = None
            try:
                crm_id = _extract_path(response.json(), self.response_id_path)
            except ValueError:
                pass  # CRM returned a non-JSON success body — still a success
            return CRMResult(
                success=True,
                crm_lead_id=str(crm_id) if crm_id is not None else None,
                status_code=response.status_code,
            )
        return CRMResult(success=False, status_code=response.status_code, error=f"crm_http_{response.status_code}")
