"""Tests for GitHub lifecycle normalization (raw webhook and parsed contract)."""

import json
from pathlib import Path

import pytest

from worker.message import parse_queue_message
from worker.normalize import (
    GitHubNoLifecycleAction,
    NormalizationError,
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


def test_missing_owner_raises_normalization_error() -> None:
    payload = {
        "action": "created",
        "repository": {"id": 1, "name": "repo", "updated_at": "2026-10-01T12:00:00Z"},
    }
    with pytest.raises(NormalizationError):
        normalize_github_queue_payload(payload)
