"""Scope-to-Snyk org mapping loaded from operator config."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from config.errors import ConfigError

ScopeSource = Literal["ado", "github"]
ResolutionKind = Literal["mapped", "default"]
SnykIntegrationType = Literal[
    "azure-repos",
    "github",
    "github-cloud",
    "github-server",
    "github-enterprise",
]

ADO_INTEGRATION_TYPE: SnykIntegrationType = "azure-repos"
GITHUB_INTEGRATION_TYPES = frozenset(
    {"github", "github-cloud", "github-server", "github-enterprise"},
)
ALL_INTEGRATION_TYPES = frozenset({ADO_INTEGRATION_TYPE}) | GITHUB_INTEGRATION_TYPES
LEGACY_SCOPE_KEYS = frozenset({"ado"})
RESERVED_SCOPE_KEYS = frozenset({"defaultSnykOrgId"})
DEFAULT_GITHUB_INTEGRATION_TYPE: SnykIntegrationType = "github"


@dataclass(frozen=True)
class ScopeEntry:
    """Scope lookup entry keyed by provider project or org name."""

    snyk_org_id: str
    integration_type: SnykIntegrationType
    source: ScopeSource
    snyk_integration_id: str | None = None


# Backward-compatible aliases used in tests and call sites.
AdoScopeEntry = ScopeEntry
GitHubScopeEntry = ScopeEntry


@dataclass(frozen=True)
class IntegrationSettings:
    """Snyk integration lookup settings for a resolved scope."""

    integration_type: SnykIntegrationType
    integration_id: str | None = None


@dataclass(frozen=True)
class ScopeMappingSettings:
    """Parsed scope mapping section from operator config."""

    default_snyk_org_id: str | None
    ado_by_project_name: dict[str, ScopeEntry]
    github_by_org_name: dict[str, ScopeEntry]
    configured_github_integration_types: frozenset[SnykIntegrationType]

    @classmethod
    def empty(cls) -> ScopeMappingSettings:
        """Return settings with no explicit mappings."""
        return cls(
            default_snyk_org_id=None,
            ado_by_project_name={},
            github_by_org_name={},
            configured_github_integration_types=frozenset(),
        )


@dataclass(frozen=True)
class ResolvedScopeMapping:
    """Successful scope mapping resolution."""

    snyk_org_id: str
    resolution: ResolutionKind


@dataclass(frozen=True)
class UnmappedScope:
    """Scope lookup key with no explicit mapping and no default org."""

    lookup_key: str
    source: ScopeSource


def _parse_azure_repos_entries(
    raw: object,
    *,
    label_prefix: str,
    target: dict[str, ScopeEntry],
) -> None:
    if raw is None:
        return
    if not isinstance(raw, list):
        raise ConfigError(f"{label_prefix} must be a list")

    for index, item in enumerate(raw):
        label = f"{label_prefix}[{index}]"
        if not isinstance(item, dict):
            raise ConfigError(f"{label} must be a mapping")
        project_name = item.get("projectName")
        snyk_org_id = item.get("snykOrgId")
        if not isinstance(project_name, str) or not project_name.strip():
            raise ConfigError(f"{label}.projectName must be a non-empty string")
        if not isinstance(snyk_org_id, str) or not snyk_org_id.strip():
            raise ConfigError(f"{label}.snykOrgId must be a non-empty string")
        integration_raw = item.get("snykIntegrationId")
        snyk_integration_id: str | None = None
        if integration_raw is not None:
            if not isinstance(integration_raw, str) or not integration_raw.strip():
                raise ConfigError(f"{label}.snykIntegrationId must be a non-empty string")
            snyk_integration_id = integration_raw.strip()
        key = project_name.strip()
        if key in target:
            raise ConfigError(f"Duplicate scopeMapping.azure-repos projectName: {key}")
        target[key] = ScopeEntry(
            snyk_org_id=snyk_org_id.strip(),
            integration_type=ADO_INTEGRATION_TYPE,
            source="ado",
            snyk_integration_id=snyk_integration_id,
        )


def _parse_github_integration_entries(
    raw: object,
    *,
    integration_type: SnykIntegrationType,
    label_prefix: str,
    target: dict[str, ScopeEntry],
) -> None:
    if raw is None:
        return
    if not isinstance(raw, list):
        raise ConfigError(f"{label_prefix} must be a list")

    for index, item in enumerate(raw):
        label = f"{label_prefix}[{index}]"
        if not isinstance(item, dict):
            raise ConfigError(f"{label} must be a mapping")
        org_name = item.get("orgName")
        snyk_org_id = item.get("snykOrgId")
        if not isinstance(org_name, str) or not org_name.strip():
            raise ConfigError(f"{label}.orgName must be a non-empty string")
        if not isinstance(snyk_org_id, str) or not snyk_org_id.strip():
            raise ConfigError(f"{label}.snykOrgId must be a non-empty string")
        integration_raw = item.get("snykIntegrationId")
        snyk_integration_id: str | None = None
        if integration_raw is not None:
            if not isinstance(integration_raw, str) or not integration_raw.strip():
                raise ConfigError(f"{label}.snykIntegrationId must be a non-empty string")
            snyk_integration_id = integration_raw.strip()
        key = org_name.strip()
        if key in target:
            raise ConfigError(f"Duplicate scopeMapping GitHub orgName: {key}")
        target[key] = ScopeEntry(
            snyk_org_id=snyk_org_id.strip(),
            integration_type=integration_type,
            source="github",
            snyk_integration_id=snyk_integration_id,
        )


def parse_scope_mapping(raw: object) -> ScopeMappingSettings:
    """Parse and validate the ``scopeMapping`` section from operator config.

    Top-level keys (other than ``defaultSnykOrgId``) MUST be Snyk integration
    types: ``azure-repos`` for ADO project entries, and ``github``,
    ``github-cloud``, ``github-server``, or ``github-enterprise`` for GitHub org
    entries.
    """
    if raw is None:
        return ScopeMappingSettings.empty()
    if not isinstance(raw, dict):
        raise ConfigError("scopeMapping must be a mapping")

    default_raw = raw.get("defaultSnykOrgId")
    default_snyk_org_id: str | None = None
    if default_raw is not None:
        if not isinstance(default_raw, str) or not default_raw.strip():
            raise ConfigError("scopeMapping.defaultSnykOrgId must be a non-empty string")
        default_snyk_org_id = default_raw.strip()

    ado_by_project_name: dict[str, ScopeEntry] = {}
    github_by_org_name: dict[str, ScopeEntry] = {}
    configured_github_integration_types: set[SnykIntegrationType] = set()

    for key, value in raw.items():
        if key in RESERVED_SCOPE_KEYS:
            continue
        if key in LEGACY_SCOPE_KEYS:
            raise ConfigError(
                f"scopeMapping.{key} is no longer supported; use integration type keys "
                f"(azure-repos for ADO, github/github-cloud/github-server/github-enterprise for GitHub)",
            )
        if key not in ALL_INTEGRATION_TYPES:
            allowed = ", ".join(sorted(ALL_INTEGRATION_TYPES))
            raise ConfigError(
                f"scopeMapping.{key} is not a supported integration type; allowed keys: {allowed}",
            )
        if key == ADO_INTEGRATION_TYPE:
            _parse_azure_repos_entries(
                value,
                label_prefix="scopeMapping.azure-repos",
                target=ado_by_project_name,
            )
        else:
            configured_github_integration_types.add(key)  # type: ignore[arg-type]
            _parse_github_integration_entries(
                value,
                integration_type=key,  # type: ignore[arg-type]
                label_prefix=f"scopeMapping.{key}",
                target=github_by_org_name,
            )

    return ScopeMappingSettings(
        default_snyk_org_id=default_snyk_org_id,
        ado_by_project_name=ado_by_project_name,
        github_by_org_name=github_by_org_name,
        configured_github_integration_types=frozenset(configured_github_integration_types),
    )


def resolve_scope_mapping(
    mapping: ScopeMappingSettings,
    *,
    source: ScopeSource,
    lookup_key: str,
) -> ResolvedScopeMapping | UnmappedScope:
    """Resolve a provider scope lookup key to a Snyk organization id."""
    if source == "ado":
        entry = mapping.ado_by_project_name.get(lookup_key)
    else:
        entry = mapping.github_by_org_name.get(lookup_key)

    if entry is not None:
        return ResolvedScopeMapping(
            snyk_org_id=entry.snyk_org_id,
            resolution="mapped",
        )

    if mapping.default_snyk_org_id is not None:
        return ResolvedScopeMapping(
            snyk_org_id=mapping.default_snyk_org_id,
            resolution="default",
        )

    return UnmappedScope(lookup_key=lookup_key, source=source)


def configured_integration_id(
    mapping: ScopeMappingSettings,
    *,
    source: ScopeSource,
    lookup_key: str,
) -> str | None:
    """Return optional configured integration id for a resolved scope lookup key."""
    return resolve_integration_settings(
        mapping,
        source=source,
        lookup_key=lookup_key,
    ).integration_id


def _default_github_integration_type(
    mapping: ScopeMappingSettings,
) -> SnykIntegrationType:
    if len(mapping.configured_github_integration_types) == 1:
        return next(iter(mapping.configured_github_integration_types))
    return DEFAULT_GITHUB_INTEGRATION_TYPE


def resolve_integration_settings(
    mapping: ScopeMappingSettings,
    *,
    source: ScopeSource,
    lookup_key: str,
) -> IntegrationSettings:
    """Return Snyk integration type and optional id for a scope lookup key."""
    if source == "ado":
        entry = mapping.ado_by_project_name.get(lookup_key)
        default_type: SnykIntegrationType = ADO_INTEGRATION_TYPE
    else:
        entry = mapping.github_by_org_name.get(lookup_key)
        default_type = _default_github_integration_type(mapping)

    if entry is not None:
        return IntegrationSettings(
            integration_type=entry.integration_type,
            integration_id=entry.snyk_integration_id,
        )

    return IntegrationSettings(integration_type=default_type, integration_id=None)
