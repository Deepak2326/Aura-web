"""Pluggable CRM integration layer.

Add a new provider by subclassing CRMClient and registering it in factory.py.
"""
from .aura_crm import AuraCRMClient
from .base import CRMClient, CRMResult, DEFAULT_FIELD_MAPPING, NullCRMClient
from .factory import build_crm_client
from .generic_rest import GenericRESTCRMClient
from .mock import MockCRMClient

__all__ = [
    "AuraCRMClient",
    "CRMClient",
    "CRMResult",
    "DEFAULT_FIELD_MAPPING",
    "NullCRMClient",
    "MockCRMClient",
    "GenericRESTCRMClient",
    "build_crm_client",
]
