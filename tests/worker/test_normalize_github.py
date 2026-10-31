"""Tests for GitHub lifecycle normalization (raw webhook and parsed contract)."""

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from worker.message import parse_queue_message
from worker.normalize import (
    GitHubNoLifecycleAction,
    NormalizationError,
    is_github_parsed_updated_body,
    normalize_github_queue_payload,
)

FIXTURES = Path(__file__).resolve().parents[2] / "data" / "fixtures"


def _load(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def test_parsed_created_normalization() -> None:
    event = normalize_github_queue_payload(_load("github_parsed_created.json"))

    assert event.source == "github"
    assert event.event_id == "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
    assert event.event_type == "repo.created"
    assert event.scope_id == "sample-org"
    assert event.github is not None
    assert event.github.org_login == "sample-org"
    assert event.ado is None
    assert event.payload["defaultBranch"] == "main"
    assert event.parsed_updated_import is False


def test_raw_renamed_normalization() -> None:
    event = normalize_github_queue_payload(_load("github_webhook_renamed.json"))

    assert event.event_type == "repo.renamed"
    assert event.repository.name == "new-name"
    assert event.payload["previousRepoName"] == "old-name"


def test_parsed_edited_branch_normalization() -> None:
    event = normalize_github_queue_payload(_load("github_parsed_edited_branch.json"))

    assert event.event_type == "repo.default_branch_changed"
    assert event.payload["previousDefaultBranch"] == "main"
    assert event.payload["defaultBranch"] == "develop"


def test_parsed_edited_description_only_skips_lifecycle() -> None:
    with pytest.raises(GitHubNoLifecycleAction):
        normalize_github_queue_payload(_load("github_parsed_edited_description.json"))


def test_parse_queue_message_sets_event_id_from_delivery_id() -> None:
    body = (FIXTURES / "github_parsed_created.json").read_text(encoding="utf-8")
    message = parse_queue_message(body)

    assert message.source == "github"
    assert message.event_id == "a1b2c3d4-e5f6-7890-abcd-ef1234567890"


def test_parsed_updated_normalizes_to_repo_created() -> None:
    payload = _load("github_parsed_updated.json")
    event = normalize_github_queue_payload(payload)

    assert is_github_parsed_updated_body(payload)
    assert event.source == "github"
    assert event.event_type == "repo.created"
    assert event.event_id == "b2c3d4e5-f6a7-8901-bcde-f12345678901"
    assert event.scope_id == "sample-org"
    assert event.github is not None
    assert event.github.org_login == "sample-org"
    assert event.ado is None
    assert event.repository.name == "sample-repo"
    assert event.payload["defaultBranch"] == "main"
    assert event.occurred_at == datetime(2026, 9, 2, 12, 0, tzinfo=UTC)
    assert event.parsed_updated_import is True
    assert event.event_type == "repo.created"


def test_parsed_updated_fixture_parses_as_github() -> None:
    body = (FIXTURES / "github_parsed_updated.json").read_text(encoding="utf-8")
    message = parse_queue_message(body)

    assert message.source == "github"
    assert message.event_id == "b2c3d4e5-f6a7-8901-bcde-f12345678901"
    assert message.provider_payload["repository"]["name"] == "sample-repo"
    assert message.provider_payload["newPropertyValues"][0]["value"] == "sample-project"


def test_lifecycle_action_with_property_values_stays_on_action_path() -> None:
    payload = _load("github_parsed_renamed.json")
    payload["newPropertyValues"] = [
        {"property_name": "azure-devops-project", "value": "sample-project"},
    ]

    event = normalize_github_queue_payload(payload)

    assert not is_github_parsed_updated_body(payload)
    assert event.event_type == "repo.renamed"


@pytest.mark.parametrize(
    ("fixture_name", "source", "event_type"),
    [
        ("github_webhook_created.json", "github", "repo.created"),
        ("github_parsed_renamed.json", "github", "repo.renamed"),
        ("github_parsed_deleted.json", "github", "repo.deleted"),
        ("github_parsed_edited_branch.json", "github", "repo.default_branch_changed"),
        ("eventgrid_ado_created.json", "ado", "repo.created"),
        ("eventgrid_ado_renamed.json", "ado", "repo.renamed"),
        ("eventgrid_ado_deleted.json", "ado", "repo.deleted"),
        ("eventgrid_ado_default_branch_changed.json", "ado", "repo.default_branch_changed"),
    ],
)
def test_existing_fixture_shapes_keep_normalized_outcomes(
    fixture_name: str,
    source: str,
    event_type: str,
) -> None:
    from worker.normalize import normalize_ado_audit_record

    message = parse_queue_message((FIXTURES / fixture_name).read_text(encoding="utf-8"))

    assert message.source == source
    if source == "github":
        event = normalize_github_queue_payload(
            message.provider_payload,
            delivery_id=message.event_id,
        )
    else:
        event = normalize_ado_audit_record(message.provider_payload)

    assert event.source == source
    assert event.event_type == event_type


def test_missing_owner_raises_normalization_error() -> None:
    payload = {
        "action": "created",
        "repository": {"id": 1, "name": "repo", "updated_at": "2026-10-01T12:00:00Z"},
    }
    with pytest.raises(NormalizationError):
        normalize_github_queue_payload(payload)
