"""Tests for Snyk integration id resolution."""

from snyk.client import SnykIntegration
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


def test_lookup_error_mentions_integration_type_not_provider_source() -> None:
    client = FakeSnykClient()
    client.integrations = [SnykIntegration(id="gh", integration_type="github-cloud")]
    resolver = IntegrationResolver(client)  # type: ignore[arg-type]

    try:
        resolver.resolve(
            org_id="org-1",
            integration_type="azure-repos",
            configured_integration_id=None,
        )
    except Exception as exc:
        assert "No azure-repos integration found" in str(exc)
        assert "ado" not in str(exc).lower() or "azure-repos" in str(exc)
    else:
        raise AssertionError("expected SnykApiError")
