"""Tests for Snyk integration id resolution."""

import pytest

from snyk.client import SnykApiError, SnykIntegration
from snyk.integration_resolver import IntegrationResolver


class FakeSnykClient:
    """Minimal fake Snyk client for integration lookup tests."""

    def __init__(self) -> None:
        self.integrations = [SnykIntegration(id="api-integration", integration_type="azure-repos")]

    def list_integrations(self, org_id: str):
        return self.integrations


def test_resolve_uses_configured_integration_id() -> None:
    resolver = IntegrationResolver(FakeSnykClient())  # type: ignore[arg-type]

    integration_id = resolver.resolve(
        org_id="org-1",
        integration_type="azure-repos",
        configured_integration_id="configured-id",
    )

    assert integration_id == "configured-id"


def test_resolve_uses_api_and_caches_result() -> None:
    resolver = IntegrationResolver(FakeSnykClient())  # type: ignore[arg-type]

    first = resolver.resolve(
        org_id="org-1",
        integration_type="azure-repos",
        configured_integration_id=None,
    )
    second = resolver.resolve(
        org_id="org-1",
        integration_type="azure-repos",
        configured_integration_id=None,
    )

    assert first == "api-integration"
    assert second == "api-integration"


def test_refresh_replaces_cached_integration_id() -> None:
    client = FakeSnykClient()
    resolver = IntegrationResolver(client)  # type: ignore[arg-type]
    resolver.resolve(
        org_id="org-1",
        integration_type="azure-repos",
        configured_integration_id=None,
    )

    client.integrations = [SnykIntegration(id="new-integration", integration_type="azure-repos")]
    refreshed = resolver.refresh(org_id="org-1", integration_type="azure-repos")

    assert refreshed == "new-integration"


@pytest.mark.parametrize(
    "integration_type",
    ["github-cloud-app", "github-server-app"],
)
def test_resolve_matches_github_app_integration_type(integration_type: str) -> None:
    client = FakeSnykClient()
    client.integrations = [
        SnykIntegration(id="github-app-integration", integration_type=integration_type),
    ]
    resolver = IntegrationResolver(client)  # type: ignore[arg-type]

    integration_id = resolver.resolve(
        org_id="org-1",
        integration_type=integration_type,  # type: ignore[arg-type]
        configured_integration_id=None,
    )

    assert integration_id == "github-app-integration"


def test_lookup_error_mentions_integration_type_not_provider_source() -> None:
    client = FakeSnykClient()
    client.integrations = [SnykIntegration(id="gh", integration_type="github-cloud-app")]
    resolver = IntegrationResolver(client)  # type: ignore[arg-type]

    with pytest.raises(SnykApiError) as error:
        resolver.resolve(
            org_id="org-1",
            integration_type="azure-repos",
            configured_integration_id=None,
        )

    assert "No azure-repos integration found" in str(error.value)
    assert "ado" not in str(error.value).lower() or "azure-repos" in str(error.value)
