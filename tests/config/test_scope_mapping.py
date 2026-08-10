"""Tests for scope mapping config parsing and resolution."""

import pytest

from config.errors import ConfigError
from config.scope_mapping import (
    AdoScopeEntry,
    GitHubScopeEntry,
    ResolvedScopeMapping,
    ScopeMappingSettings,
    UnmappedScope,
    parse_scope_mapping,
    resolve_integration_settings,
    resolve_scope_mapping,
)


def test_parse_scope_mapping_empty() -> None:
    settings = parse_scope_mapping(None)

    assert settings.default_snyk_org_id is None
    assert settings.ado_by_project_name == {}
    assert settings.github_by_org_name == {}
    assert settings.configured_github_integration_types == frozenset()


def test_parse_scope_mapping_full_section() -> None:
    settings = parse_scope_mapping(
        {
            "defaultSnykOrgId": "default-org",
            "azure-repos": [
                {
                    "projectName": "Contoso-Platform",
                    "snykOrgId": "ado-org",
                    "snykIntegrationId": "integration-1",
                },
            ],
            "github-enterprise": [
                {
                    "orgName": "contoso",
                    "snykOrgId": "github-org",
                },
            ],
        },
    )

    assert settings.default_snyk_org_id == "default-org"
    assert settings.ado_by_project_name["Contoso-Platform"] == AdoScopeEntry(
        snyk_org_id="ado-org",
        integration_type="azure-repos",
        source="ado",
        snyk_integration_id="integration-1",
    )
    assert settings.github_by_org_name["contoso"] == GitHubScopeEntry(
        snyk_org_id="github-org",
        integration_type="github-enterprise",
        source="github",
    )
    assert settings.configured_github_integration_types == frozenset({"github-enterprise"})


def test_parse_scope_mapping_rejects_legacy_ado_key() -> None:
    with pytest.raises(ConfigError, match="scopeMapping.ado is no longer supported"):
        parse_scope_mapping(
            {
                "ado": [
                    {"projectName": "proj", "snykOrgId": "org"},
                ],
            },
        )


def test_parse_scope_mapping_accepts_github_integration_type_section() -> None:
    settings = parse_scope_mapping(
        {
            "github": [
                {"orgName": "contoso", "snykOrgId": "org"},
            ],
        },
    )

    assert settings.github_by_org_name["contoso"].integration_type == "github"


def test_parse_scope_mapping_duplicate_azure_repos_project_name() -> None:
    with pytest.raises(ConfigError, match="Duplicate scopeMapping.azure-repos projectName"):
        parse_scope_mapping(
            {
                "azure-repos": [
                    {"projectName": "dup", "snykOrgId": "org-1"},
                    {"projectName": "dup", "snykOrgId": "org-2"},
                ],
            },
        )


def test_parse_scope_mapping_duplicate_github_org_name_across_sections() -> None:
    with pytest.raises(ConfigError, match="Duplicate scopeMapping GitHub orgName"):
        parse_scope_mapping(
            {
                "github": [
                    {"orgName": "dup", "snykOrgId": "org-1"},
                ],
                "github-cloud": [
                    {"orgName": "dup", "snykOrgId": "org-2"},
                ],
            },
        )


def test_resolve_scope_mapping_ado_mapped() -> None:
    mapping = ScopeMappingSettings(
        default_snyk_org_id=None,
        ado_by_project_name={
            "MyProject": AdoScopeEntry(
                snyk_org_id="mapped-org",
                integration_type="azure-repos",
                source="ado",
            ),
        },
        github_by_org_name={},
        configured_github_integration_types=frozenset(),
    )

    result = resolve_scope_mapping(mapping, source="ado", lookup_key="MyProject")

    assert result == ResolvedScopeMapping(
        snyk_org_id="mapped-org",
        resolution="mapped",
    )


def test_resolve_scope_mapping_github_mapped() -> None:
    mapping = ScopeMappingSettings(
        default_snyk_org_id=None,
        ado_by_project_name={},
        github_by_org_name={
            "contoso": GitHubScopeEntry(
                snyk_org_id="github-org",
                integration_type="github-enterprise",
                source="github",
            ),
        },
        configured_github_integration_types=frozenset({"github-enterprise"}),
    )

    result = resolve_scope_mapping(mapping, source="github", lookup_key="contoso")

    assert result == ResolvedScopeMapping(
        snyk_org_id="github-org",
        resolution="mapped",
    )


def test_resolve_scope_mapping_default_fallback() -> None:
    mapping = ScopeMappingSettings(
        default_snyk_org_id="default-org",
        ado_by_project_name={},
        github_by_org_name={},
        configured_github_integration_types=frozenset(),
    )

    result = resolve_scope_mapping(mapping, source="ado", lookup_key="unknown")

    assert result == ResolvedScopeMapping(
        snyk_org_id="default-org",
        resolution="default",
    )


def test_parse_scope_mapping_rejects_empty_integration_id() -> None:
    with pytest.raises(ConfigError, match="snykIntegrationId"):
        parse_scope_mapping(
            {
                "azure-repos": [
                    {
                        "projectName": "proj",
                        "snykOrgId": "org",
                        "snykIntegrationId": " ",
                    },
                ],
            },
        )


def test_parse_scope_mapping_assigns_integration_type_from_section_key() -> None:
    settings = parse_scope_mapping(
        {
            "azure-repos": [{"projectName": "proj", "snykOrgId": "org"}],
            "github-cloud": [{"orgName": "contoso", "snykOrgId": "org"}],
        },
    )

    assert settings.ado_by_project_name["proj"].integration_type == "azure-repos"
    assert settings.github_by_org_name["contoso"].integration_type == "github-cloud"


def test_parse_scope_mapping_rejects_unknown_top_level_key() -> None:
    with pytest.raises(ConfigError, match="not a supported integration type"):
        parse_scope_mapping(
            {
                "bitbucket": [{"projectName": "proj", "snykOrgId": "org"}],
            },
        )


def test_resolve_integration_settings_uses_defaults_for_unmapped_scope() -> None:
    settings = resolve_integration_settings(
        ScopeMappingSettings.empty(),
        source="ado",
        lookup_key="unknown",
    )

    assert settings.integration_type == "azure-repos"
    assert settings.integration_id is None


def test_resolve_integration_settings_uses_single_github_section_for_default() -> None:
    mapping = parse_scope_mapping(
        {
            "github-enterprise": [{"orgName": "contoso", "snykOrgId": "org"}],
        },
    )

    settings = resolve_integration_settings(
        mapping,
        source="github",
        lookup_key="unknown",
    )

    assert settings.integration_type == "github-enterprise"
    assert settings.integration_id is None


def test_resolve_scope_mapping_unmapped() -> None:
    mapping = ScopeMappingSettings.empty()

    result = resolve_scope_mapping(mapping, source="ado", lookup_key="unknown")

    assert result == UnmappedScope(lookup_key="unknown", source="ado")
