"""Tests for scope mapping config parsing and resolution."""

import pytest

from config.errors import ConfigError
from config.scope_mapping import (
    AdoScopeEntry,
    GitHubScopeEntry,
    PropertyExtractionError,
    ResolvedScopeMapping,
    ScopeMappingSettings,
    UnmappedScope,
    extract_scope_property,
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
                "github-cloud-app": [
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
            "github-cloud-app": [{"orgName": "contoso", "snykOrgId": "org"}],
            "github-server-app": [{"orgName": "fabrikam", "snykOrgId": "org"}],
        },
    )

    assert settings.ado_by_project_name["proj"].integration_type == "azure-repos"
    assert settings.github_by_org_name["contoso"].integration_type == "github-cloud-app"
    assert settings.github_by_org_name["fabrikam"].integration_type == "github-server-app"


@pytest.mark.parametrize(
    ("obsolete_key", "replacement"),
    [
        ("github-cloud", "github-cloud-app"),
        ("github-server", "github-server-app"),
    ],
)
def test_parse_scope_mapping_rejects_obsolete_github_app_key(
    obsolete_key: str,
    replacement: str,
) -> None:
    with pytest.raises(ConfigError, match=rf"allowed keys:.*{replacement}"):
        parse_scope_mapping(
            {
                obsolete_key: [{"orgName": "contoso", "snykOrgId": "org"}],
            },
        )


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
            "github-cloud-app": [{"orgName": "contoso", "snykOrgId": "org"}],
        },
    )

    settings = resolve_integration_settings(
        mapping,
        source="github",
        lookup_key="unknown",
    )

    assert settings.integration_type == "github-cloud-app"
    assert settings.integration_id is None


def test_resolve_scope_mapping_unmapped() -> None:
    mapping = ScopeMappingSettings.empty()

    result = resolve_scope_mapping(mapping, source="ado", lookup_key="unknown")

    assert result == UnmappedScope(lookup_key="unknown", source="ado")


def _github_extractor() -> dict[str, str]:
    return {
        "collectionPath": "data.newPropertyValues",
        "matchField": "property_name",
        "matchValue": "azure-devops-project",
        "valueField": "value",
    }


def test_parse_property_extractor_and_property_value() -> None:
    settings = parse_scope_mapping(
        {
            "propertyExtractors": {"github": _github_extractor()},
            "github-cloud-app": [
                {"orgName": "sample-org", "snykOrgId": "org-by-name"},
                {
                    "propertyValue": "sample-project",
                    "snykOrgId": "org-by-property",
                    "snykIntegrationId": "integration-9",
                },
            ],
        },
    )

    extractor = settings.property_extractors["github"]
    assert extractor.collection_path == ("data", "newPropertyValues")
    assert extractor.match_value == "azure-devops-project"
    entry = settings.github_by_property_value["sample-project"]
    assert entry.snyk_org_id == "org-by-property"
    assert entry.integration_type == "github-cloud-app"
    assert entry.snyk_integration_id == "integration-9"


@pytest.mark.parametrize(
    ("path", "match"),
    [
        ("data..values", "dotted object path"),
        ("data[0].values", "dotted object path"),
        ("../values", "dotted object path"),
        ("data.values[?(@.a)]", "dotted object path"),
    ],
)
def test_parse_property_extractor_rejects_invalid_paths(path: str, match: str) -> None:
    extractor = _github_extractor()
    extractor["collectionPath"] = path
    with pytest.raises(ConfigError, match=match):
        parse_scope_mapping({"propertyExtractors": {"github": extractor}})


def test_parse_property_extractor_rejects_unknown_provider() -> None:
    with pytest.raises(ConfigError, match="not a supported provider"):
        parse_scope_mapping(
            {"propertyExtractors": {"bitbucket": _github_extractor()}},
        )


def test_parse_property_value_requires_extractor() -> None:
    with pytest.raises(ConfigError, match="propertyExtractors.github"):
        parse_scope_mapping(
            {
                "github": [{"propertyValue": "sample-project", "snykOrgId": "org"}],
            },
        )


def test_parse_property_value_rejects_mixed_lookup_keys() -> None:
    with pytest.raises(ConfigError, match="exactly one"):
        parse_scope_mapping(
            {
                "propertyExtractors": {"github": _github_extractor()},
                "github": [
                    {
                        "orgName": "sample-org",
                        "propertyValue": "sample-project",
                        "snykOrgId": "org",
                    },
                ],
            },
        )


def test_parse_duplicate_property_value() -> None:
    with pytest.raises(ConfigError, match="Duplicate scopeMapping GitHub propertyValue"):
        parse_scope_mapping(
            {
                "propertyExtractors": {"github": _github_extractor()},
                "github": [{"propertyValue": "sample-project", "snykOrgId": "org-1"}],
                "github-enterprise": [
                    {"propertyValue": "sample-project", "snykOrgId": "org-2"},
                ],
            },
        )


def test_extract_github_property_and_resolve_without_org_fallback() -> None:
    mapping = parse_scope_mapping(
        {
            "defaultSnykOrgId": "default-org",
            "propertyExtractors": {"github": _github_extractor()},
            "github-cloud-app": [
                {"orgName": "sample-org", "snykOrgId": "org-by-name"},
                {"propertyValue": "sample-project", "snykOrgId": "org-by-property"},
            ],
        },
    )
    payload = {
        "data": {
            "newPropertyValues": [
                {"property_name": "azure-devops-project", "value": "sample-project"},
            ],
        },
    }

    extracted = extract_scope_property(mapping, source="github", payload=payload)
    resolved = resolve_scope_mapping(
        mapping,
        source="github",
        lookup_key="sample-org",
        extracted_value=extracted,
    )

    assert extracted == "sample-project"
    assert resolved == ResolvedScopeMapping(snyk_org_id="org-by-property", resolution="mapped")
    settings = resolve_integration_settings(
        mapping,
        source="github",
        lookup_key="sample-org",
        extracted_value=extracted,
    )
    assert settings.integration_type == "github-cloud-app"


def test_missing_property_path_uses_org_name() -> None:
    mapping = parse_scope_mapping(
        {
            "propertyExtractors": {"github": _github_extractor()},
            "github": [{"orgName": "sample-org", "snykOrgId": "org-by-name"}],
        },
    )

    extracted = extract_scope_property(mapping, source="github", payload={"action": "created"})
    resolved = resolve_scope_mapping(
        mapping,
        source="github",
        lookup_key="sample-org",
        extracted_value=extracted,
    )

    assert extracted is None
    assert resolved == ResolvedScopeMapping(snyk_org_id="org-by-name", resolution="mapped")


def test_unlisted_extracted_value_skips_org_name_for_default() -> None:
    mapping = parse_scope_mapping(
        {
            "defaultSnykOrgId": "default-org",
            "propertyExtractors": {"github": _github_extractor()},
            "github": [
                {"orgName": "sample-org", "snykOrgId": "org-by-name"},
                {"propertyValue": "known", "snykOrgId": "org-by-property"},
            ],
        },
    )
    payload = {
        "data": {
            "newPropertyValues": [
                {"property_name": "azure-devops-project", "value": "other-project"},
            ],
        },
    }

    extracted = extract_scope_property(mapping, source="github", payload=payload)
    resolved = resolve_scope_mapping(
        mapping,
        source="github",
        lookup_key="sample-org",
        extracted_value=extracted,
    )

    assert resolved == ResolvedScopeMapping(snyk_org_id="default-org", resolution="default")


def test_unlisted_extracted_value_without_default_is_unmapped() -> None:
    mapping = parse_scope_mapping(
        {
            "propertyExtractors": {"github": _github_extractor()},
            "github": [{"propertyValue": "known", "snykOrgId": "org-by-property"}],
        },
    )

    resolved = resolve_scope_mapping(
        mapping,
        source="github",
        lookup_key="sample-org",
        extracted_value="other-project",
    )

    assert resolved == UnmappedScope(lookup_key="other-project", source="github")


def test_extract_ado_property_from_synthetic_payload() -> None:
    mapping = parse_scope_mapping(
        {
            "propertyExtractors": {
                "azure-repos": {
                    "collectionPath": "data.properties",
                    "matchField": "name",
                    "matchValue": "team",
                    "valueField": "value",
                },
            },
            "azure-repos": [{"propertyValue": "platform", "snykOrgId": "ado-org"}],
        },
    )
    payload = {"data": {"properties": [{"name": "team", "value": "platform"}]}}

    extracted = extract_scope_property(mapping, source="ado", payload=payload)
    resolved = resolve_scope_mapping(
        mapping,
        source="ado",
        lookup_key="Contoso",
        extracted_value=extracted,
    )

    assert extracted == "platform"
    assert resolved == ResolvedScopeMapping(snyk_org_id="ado-org", resolution="mapped")


def test_extract_blank_property_value_is_absent() -> None:
    mapping = parse_scope_mapping(
        {"propertyExtractors": {"github": _github_extractor()}},
    )
    payload = {
        "data": {
            "newPropertyValues": [
                {"property_name": "azure-devops-project", "value": None},
            ],
        },
    }

    assert extract_scope_property(mapping, source="github", payload=payload) is None


def test_extract_conflicting_property_values() -> None:
    mapping = parse_scope_mapping(
        {"propertyExtractors": {"github": _github_extractor()}},
    )
    payload = {
        "data": {
            "newPropertyValues": [
                {"property_name": "azure-devops-project", "value": "one"},
                {"property_name": "azure-devops-project", "value": "two"},
            ],
        },
    }

    with pytest.raises(PropertyExtractionError, match="conflicting"):
        extract_scope_property(mapping, source="github", payload=payload)


def test_extract_wrong_json_type() -> None:
    mapping = parse_scope_mapping(
        {"propertyExtractors": {"github": _github_extractor()}},
    )

    with pytest.raises(PropertyExtractionError, match="array"):
        extract_scope_property(
            mapping,
            source="github",
            payload={"data": {"newPropertyValues": {"property_name": "azure-devops-project"}}},
        )
