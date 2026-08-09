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
    resolve_scope_mapping,
)


def test_parse_scope_mapping_empty() -> None:
    settings = parse_scope_mapping(None)

    assert settings.default_snyk_org_id is None
    assert settings.ado_by_project_name == {}
    assert settings.github_by_org_name == {}


def test_parse_scope_mapping_full_section() -> None:
    settings = parse_scope_mapping(
        {
            "defaultSnykOrgId": "default-org",
            "ado": [
                {
                    "projectName": "Contoso-Platform",
                    "snykOrgId": "ado-org",
                },
            ],
            "github": [
                {
                    "orgName": "contoso",
                    "snykOrgId": "github-org",
                },
            ],
        },
    )

    assert settings.default_snyk_org_id == "default-org"
    assert settings.ado_by_project_name["Contoso-Platform"] == AdoScopeEntry(
        project_name="Contoso-Platform",
        snyk_org_id="ado-org",
    )
    assert settings.github_by_org_name["contoso"] == GitHubScopeEntry(
        org_name="contoso",
        snyk_org_id="github-org",
    )


def test_parse_scope_mapping_duplicate_ado_project_name() -> None:
    with pytest.raises(ConfigError, match="Duplicate scopeMapping.ado projectName"):
        parse_scope_mapping(
            {
                "ado": [
                    {"projectName": "dup", "snykOrgId": "org-1"},
                    {"projectName": "dup", "snykOrgId": "org-2"},
                ],
            },
        )


def test_parse_scope_mapping_duplicate_github_org_name() -> None:
    with pytest.raises(ConfigError, match="Duplicate scopeMapping.github orgName"):
        parse_scope_mapping(
            {
                "github": [
                    {"orgName": "dup", "snykOrgId": "org-1"},
                    {"orgName": "dup", "snykOrgId": "org-2"},
                ],
            },
        )


def test_resolve_scope_mapping_ado_mapped() -> None:
    mapping = ScopeMappingSettings(
        default_snyk_org_id=None,
        ado_by_project_name={
            "MyProject": AdoScopeEntry(
                project_name="MyProject",
                snyk_org_id="mapped-org",
            ),
        },
        github_by_org_name={},
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
                org_name="contoso",
                snyk_org_id="github-org",
            ),
        },
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
    )

    result = resolve_scope_mapping(mapping, source="ado", lookup_key="unknown")

    assert result == ResolvedScopeMapping(
        snyk_org_id="default-org",
        resolution="default",
    )


def test_resolve_scope_mapping_unmapped() -> None:
    mapping = ScopeMappingSettings.empty()

    result = resolve_scope_mapping(mapping, source="ado", lookup_key="unknown")

    assert result == UnmappedScope(lookup_key="unknown", source="ado")
