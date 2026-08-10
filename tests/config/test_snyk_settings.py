"""Tests for Snyk operator config parsing."""

import pytest

from config.errors import ConfigError
from config.snyk_settings import DEFAULT_MAX_CONCURRENT_PENDING_IMPORTS, parse_snyk_settings


def test_parse_snyk_settings_defaults() -> None:
    settings = parse_snyk_settings(None)

    assert settings.max_concurrent_pending_imports == DEFAULT_MAX_CONCURRENT_PENDING_IMPORTS
    assert settings.target_removal.on_rename == "deactivate"
    assert settings.target_removal.on_default_branch_change == "deactivate"
    assert settings.target_removal.on_repo_delete == "deactivate"


def test_parse_snyk_settings_custom_values() -> None:
    settings = parse_snyk_settings(
        {
            "maxConcurrentPendingImports": 25,
            "targetRemoval": {
                "onRename": "delete",
                "onDefaultBranchChange": "delete",
                "onRepoDelete": "delete",
            },
        },
    )

    assert settings.max_concurrent_pending_imports == 25
    assert settings.target_removal.on_rename == "delete"


def test_parse_snyk_settings_rejects_invalid_removal_mode() -> None:
    with pytest.raises(ConfigError, match="onRepoDelete"):
        parse_snyk_settings({"targetRemoval": {"onRepoDelete": "destroy"}})


def test_parse_snyk_settings_rejects_invalid_pending_limit() -> None:
    with pytest.raises(ConfigError, match="maxConcurrentPendingImports"):
        parse_snyk_settings({"maxConcurrentPendingImports": 0})
