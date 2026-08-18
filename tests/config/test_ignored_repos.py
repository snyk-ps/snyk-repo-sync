"""Tests for ignore-policy parsing and matching."""

import json
from pathlib import Path

import pytest

from config.errors import ConfigError
from config.ignored_repos import (
    DEFAULT_RECONCILIATION_INTERVAL_MINUTES,
    is_ignored,
    load_ignore_policy,
    parse_ignore_policy_document,
    parse_ignored_repos_settings,
)


def test_parse_ignored_repos_settings_none() -> None:
    assert parse_ignored_repos_settings(None, config_path=Path("data/config.yaml")) is None


def test_parse_ignored_repos_settings_resolves_relative_path(tmp_path: Path) -> None:
    config_path = tmp_path / "config.yaml"
    config_path.write_text("ignoredRepos: {}\n", encoding="utf-8")

    settings = parse_ignored_repos_settings(
        {"path": "ignored-repos.yaml", "reconciliationIntervalMinutes": 30},
        config_path=config_path,
    )

    assert settings is not None
    assert settings.policy_path == (tmp_path / "ignored-repos.yaml").resolve()
    assert settings.reconciliation_interval_minutes == 30


def test_parse_ignored_repos_settings_default_interval(tmp_path: Path) -> None:
    config_path = tmp_path / "config.yaml"
    config_path.write_text("", encoding="utf-8")

    settings = parse_ignored_repos_settings({"path": "ignored-repos.yaml"}, config_path=config_path)

    assert settings is not None
    assert settings.reconciliation_interval_minutes == DEFAULT_RECONCILIATION_INTERVAL_MINUTES


def test_load_ignore_policy_yaml(tmp_path: Path) -> None:
    path = tmp_path / "ignored-repos.yaml"
    path.write_text(
        """
repos:
  - source: azure-repos
    owner: proj
    name: archived
patterns:
  - id: Disabled
    filterType: prefix
    patterns:
      - disabled-
""".strip(),
        encoding="utf-8",
    )

    policy = load_ignore_policy(path)

    assert len(policy.explicit_entries) == 1
    assert policy.explicit_entries[0].source == "azure-repos"
    assert len(policy.pattern_groups) == 1


def test_load_ignore_policy_json(tmp_path: Path) -> None:
    path = tmp_path / "ignored-repos.json"
    path.write_text(
        json.dumps(
            {
                "repos": [{"source": "github", "owner": "org", "name": "legacy"}],
                "patterns": [{"id": "Docs", "filterType": "suffix", "patterns": ["-docs"]}],
            },
        ),
        encoding="utf-8",
    )

    policy = load_ignore_policy(path)

    assert policy.explicit_entries[0].source == "github"
    assert policy.pattern_groups[0].filter_type == "suffix"


def test_parse_rejects_duplicate_explicit_entry() -> None:
    with pytest.raises(ConfigError, match="duplicate ignore entry"):
        parse_ignore_policy_document(
            {
                "repos": [
                    {"source": "azure-repos", "owner": "proj", "name": "repo"},
                    {"source": "azure-repos", "owner": "proj", "name": "repo"},
                ],
            },
        )


def test_parse_rejects_missing_source() -> None:
    with pytest.raises(ConfigError, match="source"):
        parse_ignore_policy_document({"repos": [{"owner": "proj", "name": "repo"}]})


def test_parse_rejects_invalid_regex() -> None:
    with pytest.raises(ConfigError, match="invalid regex"):
        parse_ignore_policy_document(
            {
                "patterns": [{"id": "Bad", "filterType": "regex", "patterns": ["("]}],
            },
        )


def test_is_ignored_explicit_and_pattern() -> None:
    policy = parse_ignore_policy_document(
        {
            "repos": [{"source": "azure-repos", "owner": "proj", "name": "archived"}],
            "patterns": [{"id": "Disabled", "filterType": "prefix", "patterns": ["disabled-"]}],
        },
    )

    explicit = is_ignored(policy, event_source="ado", owner="proj", repo_name="archived")
    assert explicit is not None
    assert explicit.kind == "explicit"

    pattern = is_ignored(policy, event_source="ado", owner="other", repo_name="disabled-tool")
    assert pattern is not None
    assert pattern.kind == "pattern"

    wrong_source = is_ignored(policy, event_source="ado", owner="proj", repo_name="other")
    assert wrong_source is None
