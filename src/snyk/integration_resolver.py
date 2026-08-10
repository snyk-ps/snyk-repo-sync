"""Resolve Snyk integration ids from config or API with process-local cache."""

from __future__ import annotations

import logging

from config.scope_mapping import SnykIntegrationType
from snyk.client import SnykApiError, SnykClient

logger = logging.getLogger(__name__)


class IntegrationResolver:
    """Resolve integration ids using config overrides and Snyk API lookup."""

    def __init__(self, client: SnykClient) -> None:
        self._client = client
        self._cache: dict[tuple[str, SnykIntegrationType], str] = {}

    def resolve(
        self,
        *,
        org_id: str,
        integration_type: SnykIntegrationType,
        configured_integration_id: str | None,
    ) -> str:
        """Return the integration id for a Snyk org and integration type."""
        if configured_integration_id:
            return configured_integration_id

        cache_key = (org_id, integration_type)
        cached = self._cache.get(cache_key)
        if cached is not None:
            return cached

        integration_id = self._lookup_integration_id(
            org_id=org_id,
            integration_type=integration_type,
        )
        self._cache[cache_key] = integration_id
        return integration_id

    def refresh(
        self,
        *,
        org_id: str,
        integration_type: SnykIntegrationType,
    ) -> str:
        """Force API lookup and refresh the process-local cache."""
        integration_id = self._lookup_integration_id(
            org_id=org_id,
            integration_type=integration_type,
        )
        self._cache[(org_id, integration_type)] = integration_id
        return integration_id

    def _lookup_integration_id(
        self,
        *,
        org_id: str,
        integration_type: SnykIntegrationType,
    ) -> str:
        integrations = self._client.list_integrations(org_id)
        for integration in integrations:
            if integration.integration_type == integration_type:
                return integration.id

        available_types = sorted({item.integration_type for item in integrations})
        available = ", ".join(available_types) if available_types else "none"
        raise SnykApiError(
            "No "
            f"{integration_type} integration found for Snyk org {org_id}; "
            f"available types: {available}",
        )
