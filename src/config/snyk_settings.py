"""Snyk-related operator configuration."""

from dataclasses import dataclass
from typing import Literal

from config.errors import ConfigError

RemovalMode = Literal["deactivate", "delete"]
VALID_REMOVAL_MODES = frozenset({"deactivate", "delete"})
DEFAULT_MAX_CONCURRENT_PENDING_IMPORTS = 100


@dataclass(frozen=True)
class TargetRemovalSettings:
    """Configured Snyk target removal mode per lifecycle action."""

    on_rename: RemovalMode
    on_default_branch_change: RemovalMode
    on_repo_delete: RemovalMode
    on_ignore: RemovalMode


@dataclass(frozen=True)
class SnykSettings:
    """Parsed ``snyk`` section from operator config."""

    max_concurrent_pending_imports: int
    target_removal: TargetRemovalSettings


def _parse_removal_mode(value: object, label: str) -> RemovalMode:
    if value is None:
        return "deactivate"
    if not isinstance(value, str) or not value.strip():
        raise ConfigError(f"{label} must be 'deactivate' or 'delete'")
    mode = value.strip()
    if mode not in VALID_REMOVAL_MODES:
        raise ConfigError(f"{label} must be 'deactivate' or 'delete'")
    return mode  # type: ignore[return-value]


def _parse_max_concurrent_pending_imports(value: object) -> int:
    if value is None:
        return DEFAULT_MAX_CONCURRENT_PENDING_IMPORTS
    if isinstance(value, bool) or not isinstance(value, int):
        raise ConfigError("snyk.maxConcurrentPendingImports must be a positive integer")
    if value < 1:
        raise ConfigError("snyk.maxConcurrentPendingImports must be a positive integer")
    return value


def parse_snyk_settings(raw: object) -> SnykSettings:
    """Parse and validate the ``snyk`` section from operator config.

    Args:
        raw: Raw YAML value for ``snyk`` (mapping or ``None``).

    Returns:
        Validated Snyk settings with defaults applied.

    Raises:
        ConfigError: If the section is present but invalid.
    """
    if raw is None:
        return SnykSettings(
            max_concurrent_pending_imports=DEFAULT_MAX_CONCURRENT_PENDING_IMPORTS,
            target_removal=TargetRemovalSettings(
                on_rename="deactivate",
                on_default_branch_change="deactivate",
                on_repo_delete="deactivate",
                on_ignore="deactivate",
            ),
        )
    if not isinstance(raw, dict):
        raise ConfigError("snyk must be a mapping")

    target_removal_raw = raw.get("targetRemoval")
    if target_removal_raw is None:
        target_removal = TargetRemovalSettings(
            on_rename="deactivate",
            on_default_branch_change="deactivate",
            on_repo_delete="deactivate",
            on_ignore="deactivate",
        )
    elif not isinstance(target_removal_raw, dict):
        raise ConfigError("snyk.targetRemoval must be a mapping")
    else:
        target_removal = TargetRemovalSettings(
            on_rename=_parse_removal_mode(
                target_removal_raw.get("onRename"),
                "snyk.targetRemoval.onRename",
            ),
            on_default_branch_change=_parse_removal_mode(
                target_removal_raw.get("onDefaultBranchChange"),
                "snyk.targetRemoval.onDefaultBranchChange",
            ),
            on_repo_delete=_parse_removal_mode(
                target_removal_raw.get("onRepoDelete"),
                "snyk.targetRemoval.onRepoDelete",
            ),
            on_ignore=_parse_removal_mode(
                target_removal_raw.get("onIgnore"),
                "snyk.targetRemoval.onIgnore",
            ),
        )

    return SnykSettings(
        max_concurrent_pending_imports=_parse_max_concurrent_pending_imports(
            raw.get("maxConcurrentPendingImports"),
        ),
        target_removal=target_removal,
    )
