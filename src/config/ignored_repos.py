"""Ignore-policy file parsing and repository matching."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import yaml

from config.errors import ConfigError

IgnoreSource = Literal["azure-repos", "github"]
FilterType = Literal["regex", "prefix", "suffix"]
VALID_IGNORE_SOURCES = frozenset({"azure-repos", "github"})
VALID_FILTER_TYPES = frozenset({"regex", "prefix", "suffix"})
DEFAULT_RECONCILIATION_INTERVAL_MINUTES = 15
IGNORE_POLICY_META_ROW_KEY = "ignorePolicy"
IGNORE_POLICY_META_PARTITION = "_meta"


@dataclass(frozen=True)
class IgnoredReposSettings:
    """Parsed ``ignoredRepos`` section from operator config."""

    policy_path: Path
    reconciliation_interval_minutes: int


@dataclass(frozen=True)
class ExplicitIgnoreEntry:
    """Explicit repository ignore entry."""

    source: IgnoreSource
    owner: str
    name: str


@dataclass(frozen=True)
class PatternGroup:
    """Named pattern group for repository name matching."""

    id: str
    filter_type: FilterType
    patterns: tuple[str, ...]
    compiled_regex: tuple[re.Pattern[str], ...] = ()


@dataclass(frozen=True)
class IgnorePolicy:
    """Loaded ignore policy ready for evaluation."""

    explicit_entries: tuple[ExplicitIgnoreEntry, ...]
    pattern_groups: tuple[PatternGroup, ...]


@dataclass(frozen=True)
class IgnoreMatch:
    """Result when a repository matches ignore policy."""

    kind: Literal["explicit", "pattern"]
    reason: str


def parse_ignored_repos_settings(
    raw: object,
    *,
    config_path: Path,
) -> IgnoredReposSettings | None:
    """Parse optional ``ignoredRepos`` operator config section.

    Args:
        raw: Raw YAML value for ``ignoredRepos``.
        config_path: Path to operator config file (for relative path resolution).

    Returns:
        Parsed settings, or ``None`` when the section is absent.

    Raises:
        ConfigError: If the section is present but invalid.
    """
    if raw is None:
        return None
    if not isinstance(raw, dict):
        raise ConfigError("ignoredRepos must be a mapping")

    path_raw = raw.get("path")
    if not isinstance(path_raw, str) or not path_raw.strip():
        raise ConfigError("ignoredRepos.path must be a non-empty string")

    path = Path(path_raw.strip())
    if not path.is_absolute():
        path = (config_path.parent / path).resolve()

    interval_raw = raw.get("reconciliationIntervalMinutes")
    if interval_raw is None:
        interval = DEFAULT_RECONCILIATION_INTERVAL_MINUTES
    elif isinstance(interval_raw, bool) or not isinstance(interval_raw, int):
        raise ConfigError("ignoredRepos.reconciliationIntervalMinutes must be a positive integer")
    elif interval_raw < 1:
        raise ConfigError("ignoredRepos.reconciliationIntervalMinutes must be a positive integer")
    else:
        interval = interval_raw

    return IgnoredReposSettings(
        policy_path=path,
        reconciliation_interval_minutes=interval,
    )


def load_ignore_policy(path: Path) -> IgnorePolicy:
    """Load and validate an ignore-policy file (UTF-8 YAML or JSON).

    Args:
        path: Absolute or relative path to the policy file.

    Returns:
        Validated ignore policy with compiled regex patterns.

    Raises:
        ConfigError: If the file is missing, unreadable, or invalid.
    """
    if not path.is_file():
        raise ConfigError(f"Ignore policy file not found: {path}")

    try:
        text = path.read_text(encoding="utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ConfigError(f"Ignore policy file must be UTF-8: {path}") from exc

    suffix = path.suffix.lower()
    if suffix in {".yaml", ".yml"}:
        try:
            raw = yaml.safe_load(text)
        except yaml.YAMLError as exc:
            raise ConfigError(f"Invalid YAML in ignore policy file {path}: {exc}") from exc
    elif suffix == ".json":
        try:
            raw = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ConfigError(f"Invalid JSON in ignore policy file {path}: {exc}") from exc
    else:
        raise ConfigError(
            f"Ignore policy file must use .yaml, .yml, or .json extension: {path}",
        )

    return parse_ignore_policy_document(raw, source_label=str(path))


def parse_ignore_policy_document(raw: object, *, source_label: str = "policy") -> IgnorePolicy:
    """Parse a raw ignore-policy document mapping.

    Args:
        raw: Parsed YAML/JSON document root.
        source_label: Label for error messages.

    Returns:
        Validated ignore policy.

    Raises:
        ConfigError: If the document is invalid.
    """
    if raw is None:
        raw = {}
    if not isinstance(raw, dict):
        raise ConfigError(f"{source_label} must be a mapping")

    explicit_entries = _parse_explicit_entries(raw.get("repos"), source_label=source_label)
    pattern_groups = _parse_pattern_groups(raw.get("patterns"), source_label=source_label)

    if not explicit_entries and not pattern_groups:
        raise ConfigError(f"{source_label} must include at least one repos or patterns entry")

    return IgnorePolicy(
        explicit_entries=explicit_entries,
        pattern_groups=pattern_groups,
    )


def ignore_policy_to_dict(policy: IgnorePolicy) -> dict[str, Any]:
    """Serialize an ignore policy for persistence."""
    return {
        "repos": [
            {"source": entry.source, "owner": entry.owner, "name": entry.name}
            for entry in policy.explicit_entries
        ],
        "patterns": [
            {
                "id": group.id,
                "filterType": group.filter_type,
                "patterns": list(group.patterns),
            }
            for group in policy.pattern_groups
        ],
    }


def ignore_policy_from_dict(raw: object) -> IgnorePolicy:
    """Deserialize a persisted ignore policy document."""
    return parse_ignore_policy_document(raw, source_label="persisted ignore policy")


def event_source_to_ignore_source(event_source: str) -> IgnoreSource | None:
    """Map worker event source to ignore-policy ``source`` value."""
    if event_source == "ado":
        return "azure-repos"
    if event_source == "github":
        return "github"
    return None


def is_ignored(
    policy: IgnorePolicy,
    *,
    event_source: str,
    owner: str,
    repo_name: str,
) -> IgnoreMatch | None:
    """Return match details when repository matches ignore policy."""
    ignore_source = event_source_to_ignore_source(event_source)
    if ignore_source is not None:
        for entry in policy.explicit_entries:
            if (
                entry.source == ignore_source
                and entry.owner == owner
                and entry.name == repo_name
            ):
                return IgnoreMatch(kind="explicit", reason=f"explicit:{entry.source}/{entry.owner}/{entry.name}")

    for group in policy.pattern_groups:
        if _name_matches_group(repo_name, group):
            return IgnoreMatch(kind="pattern", reason=f"pattern:{group.id}")

    return None


def _parse_explicit_entries(raw: object, *, source_label: str) -> tuple[ExplicitIgnoreEntry, ...]:
    if raw is None:
        return ()
    if not isinstance(raw, list):
        raise ConfigError(f"{source_label} repos must be a list")

    seen: set[tuple[str, str, str]] = set()
    entries: list[ExplicitIgnoreEntry] = []
    for index, item in enumerate(raw):
        if not isinstance(item, dict):
            raise ConfigError(f"{source_label} repos[{index}] must be a mapping")
        source = _require_non_empty_str(item.get("source"), f"{source_label} repos[{index}].source")
        if source not in VALID_IGNORE_SOURCES:
            raise ConfigError(
                f"{source_label} repos[{index}].source must be 'azure-repos' or 'github'",
            )
        owner = _require_non_empty_str(item.get("owner"), f"{source_label} repos[{index}].owner")
        name = _require_non_empty_str(item.get("name"), f"{source_label} repos[{index}].name")
        key = (source, owner, name)
        if key in seen:
            raise ConfigError(
                f"{source_label} contains duplicate ignore entry: source={source} owner={owner} name={name}",
            )
        seen.add(key)
        entries.append(
            ExplicitIgnoreEntry(
                source=source,  # type: ignore[arg-type]
                owner=owner,
                name=name,
            ),
        )
    return tuple(entries)


def _parse_pattern_groups(raw: object, *, source_label: str) -> tuple[PatternGroup, ...]:
    if raw is None:
        return ()
    if not isinstance(raw, list):
        raise ConfigError(f"{source_label} patterns must be a list")

    groups: list[PatternGroup] = []
    for index, item in enumerate(raw):
        if not isinstance(item, dict):
            raise ConfigError(f"{source_label} patterns[{index}] must be a mapping")
        group_id = _require_non_empty_str(item.get("id"), f"{source_label} patterns[{index}].id")
        filter_type_raw = item.get("filterType")
        if not isinstance(filter_type_raw, str) or filter_type_raw.strip() not in VALID_FILTER_TYPES:
            raise ConfigError(
                f"{source_label} patterns[{index}].filterType must be 'regex', 'prefix', or 'suffix'",
            )
        filter_type = filter_type_raw.strip()  # type: ignore[assignment]
        patterns_raw = item.get("patterns")
        if not isinstance(patterns_raw, list) or not patterns_raw:
            raise ConfigError(f"{source_label} patterns[{index}].patterns must be a non-empty list")
        patterns = tuple(
            _require_non_empty_str(value, f"{source_label} patterns[{index}].patterns[{pattern_index}]")
            for pattern_index, value in enumerate(patterns_raw)
        )
        compiled: list[re.Pattern[str]] = []
        if filter_type == "regex":
            for pattern in patterns:
                try:
                    compiled.append(re.compile(pattern))
                except re.error as exc:
                    raise ConfigError(
                        f"{source_label} patterns group '{group_id}' has invalid regex '{pattern}': {exc}",
                    ) from exc
        groups.append(
            PatternGroup(
                id=group_id,
                filter_type=filter_type,
                patterns=patterns,
                compiled_regex=tuple(compiled),
            ),
        )
    return tuple(groups)


def _name_matches_group(repo_name: str, group: PatternGroup) -> bool:
    if group.filter_type == "prefix":
        return any(repo_name.startswith(pattern) for pattern in group.patterns)
    if group.filter_type == "suffix":
        return any(repo_name.endswith(pattern) for pattern in group.patterns)
    return any(regex.search(repo_name) is not None for regex in group.compiled_regex)


def _require_non_empty_str(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ConfigError(f"Missing or invalid required field: {label}")
    return value.strip()
