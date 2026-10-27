"""Scope-to-Snyk org mapping loaded from operator config."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from config.errors import ConfigError

ScopeSource = Literal["ado", "github"]
ResolutionKind = Literal["mapped", "default"]
SnykIntegrationType = Literal[
    "azure-repos",
    "github",
    "github-cloud-app",
    "github-server-app",
    "github-enterprise",
]
ExtractorProvider = Literal["github", "azure-repos"]

ADO_INTEGRATION_TYPE: SnykIntegrationType = "azure-repos"
GITHUB_INTEGRATION_TYPES = frozenset(
    {"github", "github-cloud-app", "github-server-app", "github-enterprise"},
)
ALL_INTEGRATION_TYPES = frozenset({ADO_INTEGRATION_TYPE}) | GITHUB_INTEGRATION_TYPES
EXTRACTOR_PROVIDERS = frozenset({"github", "azure-repos"})
LEGACY_SCOPE_KEYS = frozenset({"ado"})
RESERVED_SCOPE_KEYS = frozenset({"defaultSnykOrgId", "propertyExtractors"})
DEFAULT_GITHUB_INTEGRATION_TYPE: SnykIntegrationType = "github"
_PATH_FORBIDDEN_CHARS = "[]*?()"


class PropertyExtractionError(ValueError):
    """Raised when a configured property path is present but invalid."""


@dataclass(frozen=True)
class ScopeEntry:
    """Scope lookup entry keyed by provider project, org, or property value."""

    snyk_org_id: str
    integration_type: SnykIntegrationType
    source: ScopeSource
    snyk_integration_id: str | None = None


# Backward-compatible aliases used in tests and call sites.
AdoScopeEntry = ScopeEntry
GitHubScopeEntry = ScopeEntry


@dataclass(frozen=True)
class PropertyExtractor:
    """Config path that reads one property value from a provider message."""

    collection_path: tuple[str, ...]
    match_field: str
    match_value: str
    value_field: str


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
    ado_by_property_value: dict[str, ScopeEntry] = field(default_factory=dict)
    github_by_property_value: dict[str, ScopeEntry] = field(default_factory=dict)
    property_extractors: dict[str, PropertyExtractor] = field(default_factory=dict)

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


def _parse_collection_path(raw: object, *, label: str) -> tuple[str, ...]:
    if not isinstance(raw, str) or not raw.strip():
        raise ConfigError(f"{label} must be a non-empty string")
    if raw != raw.strip() or any(char in raw for char in _PATH_FORBIDDEN_CHARS):
        raise ConfigError(f"{label} must be a dotted object path")
    parts = tuple(raw.split("."))
    if any(part == "" or part == ".." for part in parts):
        raise ConfigError(f"{label} must be a dotted object path")
    return parts


def _parse_required_str(item: dict[str, Any], key: str, *, label: str) -> str:
    value = item.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ConfigError(f"{label}.{key} must be a non-empty string")
    return value.strip()


def _parse_property_extractors(raw: object) -> dict[str, PropertyExtractor]:
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise ConfigError("scopeMapping.propertyExtractors must be a mapping")

    extractors: dict[str, PropertyExtractor] = {}
    for key, value in raw.items():
        label = f"scopeMapping.propertyExtractors.{key}"
        if key not in EXTRACTOR_PROVIDERS:
            allowed = ", ".join(sorted(EXTRACTOR_PROVIDERS))
            raise ConfigError(f"{label} is not a supported provider; allowed keys: {allowed}")
        if not isinstance(value, dict):
            raise ConfigError(f"{label} must be a mapping")
        extractors[key] = PropertyExtractor(
            collection_path=_parse_collection_path(
                value.get("collectionPath"),
                label=f"{label}.collectionPath",
            ),
            match_field=_parse_required_str(value, "matchField", label=label),
            match_value=_parse_required_str(value, "matchValue", label=label),
            value_field=_parse_required_str(value, "valueField", label=label),
        )
    return extractors


def _optional_integration_id(item: dict[str, Any], *, label: str) -> str | None:
    integration_raw = item.get("snykIntegrationId")
    if integration_raw is None:
        return None
    if not isinstance(integration_raw, str) or not integration_raw.strip():
        raise ConfigError(f"{label}.snykIntegrationId must be a non-empty string")
    return integration_raw.strip()


def _present_lookup_key(item: dict[str, Any], field_name: str, *, label: str) -> str | None:
    if field_name not in item or item.get(field_name) is None:
        return None
    value = item.get(field_name)
    if not isinstance(value, str) or not value.strip():
        raise ConfigError(f"{label}.{field_name} must be a non-empty string")
    return value.strip()


def _parse_scope_entries(
    raw: object,
    *,
    name_field: str,
    integration_type: SnykIntegrationType,
    source: ScopeSource,
    label_prefix: str,
    name_target: dict[str, ScopeEntry],
    property_target: dict[str, ScopeEntry],
    duplicate_name_message: str,
    duplicate_property_message: str,
) -> None:
    if raw is None:
        return
    if not isinstance(raw, list):
        raise ConfigError(f"{label_prefix} must be a list")

    for index, item in enumerate(raw):
        label = f"{label_prefix}[{index}]"
        if not isinstance(item, dict):
            raise ConfigError(f"{label} must be a mapping")
        name_key = _present_lookup_key(item, name_field, label=label)
        property_key = _present_lookup_key(item, "propertyValue", label=label)
        if (name_key is None) == (property_key is None):
            raise ConfigError(
                f"{label} must set exactly one of {name_field} or propertyValue",
            )
        snyk_org_id = item.get("snykOrgId")
        if not isinstance(snyk_org_id, str) or not snyk_org_id.strip():
            raise ConfigError(f"{label}.snykOrgId must be a non-empty string")
        entry = ScopeEntry(
            snyk_org_id=snyk_org_id.strip(),
            integration_type=integration_type,
            source=source,
            snyk_integration_id=_optional_integration_id(item, label=label),
        )
        if name_key is not None:
            if name_key in name_target:
                raise ConfigError(duplicate_name_message.format(key=name_key))
            name_target[name_key] = entry
            continue
        assert property_key is not None
        if property_key in property_target:
            raise ConfigError(duplicate_property_message.format(key=property_key))
        property_target[property_key] = entry


def parse_scope_mapping(raw: object) -> ScopeMappingSettings:
    """Parse and validate the ``scopeMapping`` section from operator config.

    Top-level keys other than ``defaultSnykOrgId`` and ``propertyExtractors``
    MUST be Snyk integration types. ``propertyValue`` rows require an extractor
    for that provider.
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

    property_extractors = _parse_property_extractors(raw.get("propertyExtractors"))
    ado_by_project_name: dict[str, ScopeEntry] = {}
    ado_by_property_value: dict[str, ScopeEntry] = {}
    github_by_org_name: dict[str, ScopeEntry] = {}
    github_by_property_value: dict[str, ScopeEntry] = {}
    configured_github_integration_types: set[SnykIntegrationType] = set()

    for key, value in raw.items():
        if key in RESERVED_SCOPE_KEYS:
            continue
        if key in LEGACY_SCOPE_KEYS:
            raise ConfigError(
                f"scopeMapping.{key} is no longer supported; use integration type keys "
                "(azure-repos for ADO, "
                "github/github-cloud-app/github-server-app/github-enterprise for GitHub)",
            )
        if key not in ALL_INTEGRATION_TYPES:
            allowed = ", ".join(sorted(ALL_INTEGRATION_TYPES | {"propertyExtractors"}))
            raise ConfigError(
                f"scopeMapping.{key} is not a supported integration type; allowed keys: {allowed}",
            )
        if key == ADO_INTEGRATION_TYPE:
            _parse_scope_entries(
                value,
                name_field="projectName",
                integration_type=ADO_INTEGRATION_TYPE,
                source="ado",
                label_prefix="scopeMapping.azure-repos",
                name_target=ado_by_project_name,
                property_target=ado_by_property_value,
                duplicate_name_message="Duplicate scopeMapping.azure-repos projectName: {key}",
                duplicate_property_message=(
                    "Duplicate scopeMapping.azure-repos propertyValue: {key}"
                ),
            )
        else:
            configured_github_integration_types.add(key)  # type: ignore[arg-type]
            _parse_scope_entries(
                value,
                name_field="orgName",
                integration_type=key,  # type: ignore[arg-type]
                source="github",
                label_prefix=f"scopeMapping.{key}",
                name_target=github_by_org_name,
                property_target=github_by_property_value,
                duplicate_name_message="Duplicate scopeMapping GitHub orgName: {key}",
                duplicate_property_message="Duplicate scopeMapping GitHub propertyValue: {key}",
            )

    if ado_by_property_value and "azure-repos" not in property_extractors:
        raise ConfigError(
            "scopeMapping propertyValue entries require propertyExtractors.azure-repos",
        )
    if github_by_property_value and "github" not in property_extractors:
        raise ConfigError(
            "scopeMapping propertyValue entries require propertyExtractors.github",
        )

    return ScopeMappingSettings(
        default_snyk_org_id=default_snyk_org_id,
        ado_by_project_name=ado_by_project_name,
        github_by_org_name=github_by_org_name,
        configured_github_integration_types=frozenset(configured_github_integration_types),
        ado_by_property_value=ado_by_property_value,
        github_by_property_value=github_by_property_value,
        property_extractors=property_extractors,
    )


def _extractor_provider(source: ScopeSource) -> ExtractorProvider:
    if source == "ado":
        return "azure-repos"
    return "github"


def _property_entries(
    mapping: ScopeMappingSettings,
    source: ScopeSource,
) -> dict[str, ScopeEntry]:
    if source == "ado":
        return mapping.ado_by_property_value
    return mapping.github_by_property_value


def _name_entries(
    mapping: ScopeMappingSettings,
    source: ScopeSource,
) -> dict[str, ScopeEntry]:
    if source == "ado":
        return mapping.ado_by_project_name
    return mapping.github_by_org_name


def extract_scope_property(
    mapping: ScopeMappingSettings,
    *,
    source: ScopeSource,
    payload: dict[str, Any],
) -> str | None:
    """Return the configured property value from a received JSON object.

    Raises:
        PropertyExtractionError: When the path is present but has the wrong
            shape, or matching elements disagree.
    """
    extractor = mapping.property_extractors.get(_extractor_provider(source))
    if extractor is None:
        return None

    node: Any = payload
    for index, segment in enumerate(extractor.collection_path):
        if not isinstance(node, dict):
            raise PropertyExtractionError(
                "property extractor path encountered a non-object value",
            )
        if segment not in node:
            return None
        node = node[segment]
        if index == len(extractor.collection_path) - 1:
            break

    if not isinstance(node, list):
        raise PropertyExtractionError("property extractor path must end at an array")

    values: list[str] = []
    for item in node:
        if not isinstance(item, dict):
            raise PropertyExtractionError("property extractor array elements must be objects")
        if item.get(extractor.match_field) != extractor.match_value:
            continue
        raw_value = item.get(extractor.value_field)
        if raw_value is None:
            continue
        if not isinstance(raw_value, str):
            raise PropertyExtractionError("property extractor value must be a string or null")
        if not raw_value.strip():
            continue
        values.append(raw_value.strip())

    unique = set(values)
    if len(unique) > 1:
        raise PropertyExtractionError("property extractor found conflicting values")
    if len(unique) == 1:
        return values[0]
    return None


def resolve_scope_mapping(
    mapping: ScopeMappingSettings,
    *,
    source: ScopeSource,
    lookup_key: str,
    extracted_value: str | None = None,
) -> ResolvedScopeMapping | UnmappedScope:
    """Resolve a provider scope lookup key to a Snyk organization id."""
    if extracted_value is not None:
        entry = _property_entries(mapping, source).get(extracted_value)
        effective_key = extracted_value
    else:
        entry = _name_entries(mapping, source).get(lookup_key)
        effective_key = lookup_key

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

    return UnmappedScope(lookup_key=effective_key, source=source)


def configured_integration_id(
    mapping: ScopeMappingSettings,
    *,
    source: ScopeSource,
    lookup_key: str,
    extracted_value: str | None = None,
) -> str | None:
    """Return optional configured integration id for a resolved scope lookup key."""
    return resolve_integration_settings(
        mapping,
        source=source,
        lookup_key=lookup_key,
        extracted_value=extracted_value,
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
    extracted_value: str | None = None,
) -> IntegrationSettings:
    """Return Snyk integration type and optional id for a scope lookup key."""
    if source == "ado":
        default_type: SnykIntegrationType = ADO_INTEGRATION_TYPE
    else:
        default_type = _default_github_integration_type(mapping)

    if extracted_value is not None:
        entry = _property_entries(mapping, source).get(extracted_value)
    else:
        entry = _name_entries(mapping, source).get(lookup_key)

    if entry is not None:
        return IntegrationSettings(
            integration_type=entry.integration_type,
            integration_id=entry.snyk_integration_id,
        )

    return IntegrationSettings(integration_type=default_type, integration_id=None)
