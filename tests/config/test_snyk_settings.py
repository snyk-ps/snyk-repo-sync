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
    assert settings.target_removal.on_ignore == "deactivate"
    assert settings.migrate_ignores is True


def test_parse_snyk_settings_custom_values() -> None:
    settings = parse_snyk_settings(
        {
            "maxConcurrentPendingImports": 25,
            "targetRemoval": {
                "onRename": "delete",
                "onDefaultBranchChange": "delete",
                "onRepoDelete": "delete",
                "onIgnore": "delete",
            },
        },
    )

    assert settings.max_concurrent_pending_imports == 25
    assert settings.target_removal.on_rename == "delete"
    assert settings.target_removal.on_ignore == "delete"


def test_parse_snyk_settings_rejects_invalid_removal_mode() -> None:
    with pytest.raises(ConfigError, match="onRepoDelete"):
        parse_snyk_settings({"targetRemoval": {"onRepoDelete": "destroy"}})


def test_parse_snyk_settings_migrate_ignores_explicit_values() -> None:
    assert parse_snyk_settings({}).migrate_ignores is True
    assert parse_snyk_settings({"migrateIgnores": True}).migrate_ignores is True
    assert parse_snyk_settings({"migrateIgnores": False}).migrate_ignores is False


def test_parse_snyk_settings_rejects_non_boolean_migrate_ignores() -> None:
    with pytest.raises(ConfigError, match="migrateIgnores"):
        parse_snyk_settings({"migrateIgnores": "true"})


def test_parse_snyk_settings_rejects_invalid_pending_limit() -> None:
    with pytest.raises(ConfigError, match="maxConcurrentPendingImports"):
        parse_snyk_settings({"maxConcurrentPendingImports": 0})
