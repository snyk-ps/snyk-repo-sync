"""Scope-to-Snyk org mapping loaded from operator config."""

from dataclasses import dataclass
from typing import Literal

from config.errors import ConfigError

ScopeSource = Literal["ado", "github"]
ResolutionKind = Literal["mapped", "default"]


@dataclass(frozen=True)
class AdoScopeEntry:
    """ADO project name to Snyk org mapping."""

    project_name: str
    snyk_org_id: str


@dataclass(frozen=True)
class GitHubScopeEntry:
    """GitHub organization login to Snyk org mapping."""

    org_name: str
    snyk_org_id: str


@dataclass(frozen=True)
class ScopeMappingSettings:
    """Parsed scope mapping section from operator config."""

    default_snyk_org_id: str | None
    ado_by_project_name: dict[str, AdoScopeEntry]
    github_by_org_name: dict[str, GitHubScopeEntry]

    @classmethod
    def empty(cls) -> ScopeMappingSettings:
        """Return settings with no explicit mappings."""
        return cls(default_snyk_org_id=None, ado_by_project_name={}, github_by_org_name={})


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


def _parse_ado_entries(raw: object) -> dict[str, AdoScopeEntry]:
    if raw is None:
        return {}
    if not isinstance(raw, list):
        raise ConfigError("scopeMapping.ado must be a list")

    entries: dict[str, AdoScopeEntry] = {}
    for index, item in enumerate(raw):
        label = f"scopeMapping.ado[{index}]"
        if not isinstance(item, dict):
            raise ConfigError(f"{label} must be a mapping")
        project_name = item.get("projectName")
        snyk_org_id = item.get("snykOrgId")
        if not isinstance(project_name, str) or not project_name.strip():
            raise ConfigError(f"{label}.projectName must be a non-empty string")
        if not isinstance(snyk_org_id, str) or not snyk_org_id.strip():
            raise ConfigError(f"{label}.snykOrgId must be a non-empty string")
        key = project_name.strip()
        if key in entries:
            raise ConfigError(f"Duplicate scopeMapping.ado projectName: {key}")
        entries[key] = AdoScopeEntry(
            project_name=key,
            snyk_org_id=snyk_org_id.strip(),
        )
    return entries


def _parse_github_entries(raw: object) -> dict[str, GitHubScopeEntry]:
    if raw is None:
        return {}
    if not isinstance(raw, list):
        raise ConfigError("scopeMapping.github must be a list")

    entries: dict[str, GitHubScopeEntry] = {}
    for index, item in enumerate(raw):
        label = f"scopeMapping.github[{index}]"
        if not isinstance(item, dict):
            raise ConfigError(f"{label} must be a mapping")
        org_name = item.get("orgName")
        snyk_org_id = item.get("snykOrgId")
        if not isinstance(org_name, str) or not org_name.strip():
            raise ConfigError(f"{label}.orgName must be a non-empty string")
        if not isinstance(snyk_org_id, str) or not snyk_org_id.strip():
            raise ConfigError(f"{label}.snykOrgId must be a non-empty string")
        key = org_name.strip()
        if key in entries:
            raise ConfigError(f"Duplicate scopeMapping.github orgName: {key}")
        entries[key] = GitHubScopeEntry(
            org_name=key,
            snyk_org_id=snyk_org_id.strip(),
        )
    return entries


def parse_scope_mapping(raw: object) -> ScopeMappingSettings:
    """Parse and validate the ``scopeMapping`` section from operator config.

    Args:
        raw: Raw YAML value for ``scopeMapping`` (mapping or ``None``).

    Returns:
        Validated scope mapping settings.

    Raises:
        ConfigError: If the section is present but invalid.
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

    return ScopeMappingSettings(
        default_snyk_org_id=default_snyk_org_id,
        ado_by_project_name=_parse_ado_entries(raw.get("ado")),
        github_by_org_name=_parse_github_entries(raw.get("github")),
    )


def resolve_scope_mapping(
    mapping: ScopeMappingSettings,
    *,
    source: ScopeSource,
    lookup_key: str,
) -> ResolvedScopeMapping | UnmappedScope:
    """Resolve a provider scope lookup key to a Snyk organization id.

    Args:
        mapping: Parsed scope mapping settings.
        source: Provider source (``ado`` or ``github``).
        lookup_key: ADO project name or GitHub org login.

    Returns:
        Resolved mapping or unmapped scope indicator.
    """
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
