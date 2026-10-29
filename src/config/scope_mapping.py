"""Scope-to-Snyk org mapping loaded from operator config."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Any, Literal, Protocol

from config.errors import ConfigError

ScopeSource = Literal["ado", "github"]
ResolutionKind = Literal["mapped", "org_name", "stored", "default"]
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
RESERVED_SCOPE_KEYS = frozenset({"defaultSnykOrgId", "propertyExtractors", "snykGroupId"})
_SECTION_OBJECT_KEYS = frozenset({"entries", "matchSnykOrgName"})
_MATCH_KEYS = frozenset({"enabled", "normalize"})


class GroupOrgRecord(Protocol):
    """Organization id and name returned by a group org loader."""

    id: str
    name: str


GroupOrgLoader = Callable[[str], Sequence[GroupOrgRecord]]
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
class OrgNameMatchSettings:
    """Org-name match options for one integration section."""

    enabled: bool
    normalize: bool
    integration_type: SnykIntegrationType


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
    snyk_group_id: str | None = None
    ado_org_name_match: OrgNameMatchSettings | None = None
    github_org_name_match: OrgNameMatchSettings | None = None

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
    integration_type: SnykIntegrationType | None = None
    integration_id: str | None = None
    matched_org_name: str | None = None
    candidate: str | None = None


@dataclass(frozen=True)
class UnmappedScope:
    """Scope lookup key with no explicit mapping and no default org."""

    lookup_key: str
    source: ScopeSource


@dataclass(frozen=True)
class AmbiguousOrgNameMatch:
    """Candidate matched more than one Snyk organization name."""

    lookup_key: str
    source: ScopeSource
    candidate: str
    matched_org_names: tuple[str, ...]


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


def _parse_required_bool(item: dict[str, Any], key: str, *, label: str) -> bool:
    if key not in item or not isinstance(item.get(key), bool):
        raise ConfigError(f"{label}.{key} must be a boolean")
    return bool(item[key])


def _parse_match_snyk_org_name(
    raw: object,
    *,
    label: str,
    integration_type: SnykIntegrationType,
) -> OrgNameMatchSettings:
    if not isinstance(raw, dict):
        raise ConfigError(f"{label} must be a mapping")
    extra = sorted(set(raw) - _MATCH_KEYS)
    if extra:
        names = ", ".join(extra)
        raise ConfigError(f"{label} contains unsupported keys: {names}")
    return OrgNameMatchSettings(
        enabled=_parse_required_bool(raw, "enabled", label=label),
        normalize=_parse_required_bool(raw, "normalize", label=label),
        integration_type=integration_type,
    )


def _assign_name_match(
    current: OrgNameMatchSettings | None,
    new: OrgNameMatchSettings | None,
    *,
    provider_label: str,
) -> OrgNameMatchSettings | None:
    if new is None:
        return current
    if current is not None and current.enabled and new.enabled:
        raise ConfigError(
            f"scopeMapping allows matchSnykOrgName.enabled on only one {provider_label} section",
        )
    if current is None or new.enabled:
        return new
    return current


def _parse_integration_section(
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
) -> OrgNameMatchSettings | None:
    """Parse a list section or an object section with entries and name match."""
    if isinstance(raw, list):
        _parse_scope_entries(
            raw,
            name_field=name_field,
            integration_type=integration_type,
            source=source,
            label_prefix=label_prefix,
            name_target=name_target,
            property_target=property_target,
            duplicate_name_message=duplicate_name_message,
            duplicate_property_message=duplicate_property_message,
        )
        return None
    if not isinstance(raw, dict):
        raise ConfigError(f"{label_prefix} must be a list or a mapping")
    extra = sorted(set(raw) - _SECTION_OBJECT_KEYS)
    if extra:
        names = ", ".join(extra)
        raise ConfigError(f"{label_prefix} contains unsupported keys: {names}")
    if "entries" in raw:
        _parse_scope_entries(
            raw.get("entries"),
            name_field=name_field,
            integration_type=integration_type,
            source=source,
            label_prefix=f"{label_prefix}.entries",
            name_target=name_target,
            property_target=property_target,
            duplicate_name_message=duplicate_name_message,
            duplicate_property_message=duplicate_property_message,
        )
    match_raw = raw.get("matchSnykOrgName")
    if match_raw is None:
        return None
    return _parse_match_snyk_org_name(
        match_raw,
        label=f"{label_prefix}.matchSnykOrgName",
        integration_type=integration_type,
    )


def parse_scope_mapping(raw: object) -> ScopeMappingSettings:
    """Parse and validate the ``scopeMapping`` section from operator config.

    Top-level keys other than ``defaultSnykOrgId``, ``propertyExtractors``, and
    ``snykGroupId`` MUST be Snyk integration types. ``propertyValue`` rows
    require an extractor for that provider. An integration section is a list
    of static rows or a mapping with ``entries`` and ``matchSnykOrgName``.
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

    group_raw = raw.get("snykGroupId")
    snyk_group_id: str | None = None
    if group_raw is not None:
        if not isinstance(group_raw, str) or not group_raw.strip():
            raise ConfigError("scopeMapping.snykGroupId must be a non-empty string")
        snyk_group_id = group_raw.strip()

    property_extractors = _parse_property_extractors(raw.get("propertyExtractors"))
    ado_by_project_name: dict[str, ScopeEntry] = {}
    ado_by_property_value: dict[str, ScopeEntry] = {}
    github_by_org_name: dict[str, ScopeEntry] = {}
    github_by_property_value: dict[str, ScopeEntry] = {}
    configured_github_integration_types: set[SnykIntegrationType] = set()
    ado_org_name_match: OrgNameMatchSettings | None = None
    github_org_name_match: OrgNameMatchSettings | None = None

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
            allowed = ", ".join(
                sorted(ALL_INTEGRATION_TYPES | {"propertyExtractors", "snykGroupId"}),
            )
            raise ConfigError(
                f"scopeMapping.{key} is not a supported integration type; allowed keys: {allowed}",
            )
        if key == ADO_INTEGRATION_TYPE:
            ado_org_name_match = _assign_name_match(
                ado_org_name_match,
                _parse_integration_section(
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
                ),
                provider_label="azure-repos",
            )
        else:
            configured_github_integration_types.add(key)  # type: ignore[arg-type]
            github_org_name_match = _assign_name_match(
                github_org_name_match,
                _parse_integration_section(
                    value,
                    name_field="orgName",
                    integration_type=key,  # type: ignore[arg-type]
                    source="github",
                    label_prefix=f"scopeMapping.{key}",
                    name_target=github_by_org_name,
                    property_target=github_by_property_value,
                    duplicate_name_message="Duplicate scopeMapping GitHub orgName: {key}",
                    duplicate_property_message="Duplicate scopeMapping GitHub propertyValue: {key}",
                ),
                provider_label="GitHub",
            )

    if ado_by_property_value and "azure-repos" not in property_extractors:
        raise ConfigError(
            "scopeMapping propertyValue entries require propertyExtractors.azure-repos",
        )
    if github_by_property_value and "github" not in property_extractors:
        raise ConfigError(
            "scopeMapping propertyValue entries require propertyExtractors.github",
        )
    name_match_enabled = any(
        settings is not None and settings.enabled
        for settings in (ado_org_name_match, github_org_name_match)
    )
    if name_match_enabled and not snyk_group_id:
        raise ConfigError(
            "scopeMapping.snykGroupId must be a non-empty string when "
            "matchSnykOrgName.enabled is true",
        )

    return ScopeMappingSettings(
        default_snyk_org_id=default_snyk_org_id,
        ado_by_project_name=ado_by_project_name,
        github_by_org_name=github_by_org_name,
        configured_github_integration_types=frozenset(configured_github_integration_types),
        ado_by_property_value=ado_by_property_value,
        github_by_property_value=github_by_property_value,
        property_extractors=property_extractors,
        snyk_group_id=snyk_group_id,
        ado_org_name_match=ado_org_name_match,
        github_org_name_match=github_org_name_match,
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


def _valid_stored_org(
    stored_org_id: str | None,
    stored_integration_type: str | None,
) -> tuple[str, SnykIntegrationType] | None:
    if not isinstance(stored_org_id, str) or not stored_org_id.strip():
        return None
    if stored_integration_type not in ALL_INTEGRATION_TYPES:
        return None
    return stored_org_id.strip(), stored_integration_type  # type: ignore[return-value]


def _name_match_settings(
    mapping: ScopeMappingSettings,
    source: ScopeSource,
) -> OrgNameMatchSettings | None:
    if source == "ado":
        return mapping.ado_org_name_match
    return mapping.github_org_name_match


def _resolve_org_name(
    mapping: ScopeMappingSettings,
    *,
    source: ScopeSource,
    lookup_key: str,
    candidate: str,
    group_org_loader: GroupOrgLoader | None,
) -> ResolvedScopeMapping | AmbiguousOrgNameMatch | None:
    """Match the candidate to a group org name, or continue when nothing matches."""
    settings = _name_match_settings(mapping, source)
    if settings is None or not settings.enabled:
        return None
    # Import lazily so loading config does not cycle through the Snyk package.
    from snyk.client import SnykApiError
    from snyk.group_orgs import match_group_orgs

    group_id = mapping.snyk_group_id
    if not group_id or group_org_loader is None:
        raise SnykApiError(
            "Snyk API GET /v1/group/{groupId}/orgs is unavailable",
        )
    orgs = group_org_loader(group_id)
    if not isinstance(orgs, list):
        raise SnykApiError(
            f"Snyk API GET /v1/group/{group_id}/orgs returned an invalid group org list",
        )
    matches = match_group_orgs(candidate, orgs, normalize=settings.normalize)
    if len(matches) > 1:
        return AmbiguousOrgNameMatch(
            lookup_key=lookup_key,
            source=source,
            candidate=candidate,
            matched_org_names=tuple(org.name for org in matches),
        )
    if len(matches) == 1:
        matched = matches[0]
        return ResolvedScopeMapping(
            snyk_org_id=matched.id,
            resolution="org_name",
            integration_type=settings.integration_type,
            matched_org_name=matched.name,
            candidate=candidate,
        )
    return None


def resolve_scope_mapping(
    mapping: ScopeMappingSettings,
    *,
    source: ScopeSource,
    lookup_key: str,
    extracted_value: str | None = None,
    stored_org_id: str | None = None,
    stored_integration_type: str | None = None,
    group_org_loader: GroupOrgLoader | None = None,
) -> ResolvedScopeMapping | UnmappedScope | AmbiguousOrgNameMatch:
    """Resolve a provider scope lookup key to a Snyk organization id.

    Stops at the first success: static row, org-name match, non-empty stored
    org id, then ``defaultSnykOrgId``. A group org list failure raises
    ``SnykApiError`` and does not continue. Two or more name matches stop
    without a Snyk org.
    """
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
            integration_type=entry.integration_type,
            integration_id=entry.snyk_integration_id,
        )

    name_match = _resolve_org_name(
        mapping,
        source=source,
        lookup_key=effective_key,
        candidate=effective_key,
        group_org_loader=group_org_loader,
    )
    if name_match is not None:
        return name_match

    stored = _valid_stored_org(stored_org_id, stored_integration_type)
    if stored is not None:
        org_id, integration_type = stored
        return ResolvedScopeMapping(
            snyk_org_id=org_id,
            resolution="stored",
            integration_type=integration_type,
        )

    if mapping.default_snyk_org_id is not None:
        if source == "ado":
            default_type: SnykIntegrationType = ADO_INTEGRATION_TYPE
        else:
            default_type = _default_github_integration_type(mapping)
        return ResolvedScopeMapping(
            snyk_org_id=mapping.default_snyk_org_id,
            resolution="default",
            integration_type=default_type,
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
