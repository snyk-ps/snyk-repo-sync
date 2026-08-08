"""Tests for ADO lifecycle event normalization."""

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from worker.message import parse_queue_message
from worker.normalize import NormalizationError, normalize_ado_audit_record, strip_branch_ref

FIXTURES = Path(__file__).resolve().parents[2] / "data" / "fixtures"


def _audit_from_fixture(name: str) -> dict:
    body = (FIXTURES / name).read_text(encoding="utf-8")
    message = parse_queue_message(body)
    assert message.source == "ado"
    return message.provider_payload


def test_strip_branch_ref() -> None:
    assert strip_branch_ref("refs/heads/main") == "main"
    assert strip_branch_ref("main") == "main"


def test_normalize_default_branch_changed_fixture() -> None:
    audit = _audit_from_fixture("eventgrid_ado_default_branch_changed.json")
    event = normalize_ado_audit_record(audit)

    assert event.event_type == "repo.default_branch_changed"
    assert event.event_id == "acf86b70-4ec3-4052-9e0b-fbcdd5109c1f"
    assert event.scope_id == "da9734d4-a91a-4f03-814b-ecc721fe24d1"
    assert event.repository_id == "90bd6b5e-0fbd-4edc-a10e-6604fe76027d"
    assert event.occurred_at == datetime(
        2026, 8, 6, 17, 31, 52, 327384, tzinfo=timezone.utc
    )
    assert event.ado.org_id == "c638432a-7f35-450f-984f-372b9d46a376"
    assert event.ado.org_display_name == "torstencannell (Organization)"
    assert event.ado.project_id == event.scope_id
    assert event.ado.project_name == "snykDemoProject"
    assert event.repository.name == "juice-shop.git"
    assert event.payload == {
        "defaultBranch": "master",
        "previousDefaultBranch": "develop",
    }


def test_normalize_created_fixture() -> None:
    audit = _audit_from_fixture("eventgrid_ado_created.json")
    event = normalize_ado_audit_record(audit)

    assert event.event_type == "repo.created"
    assert event.payload == {"defaultBranch": "main"}


def test_normalize_renamed_fixture() -> None:
    audit = _audit_from_fixture("eventgrid_ado_renamed.json")
    event = normalize_ado_audit_record(audit)

    assert event.event_type == "repo.renamed"
    assert event.payload == {"previousRepoName": "old-repo.git"}


def test_normalize_deleted_fixture() -> None:
    audit = _audit_from_fixture("eventgrid_ado_deleted.json")
    event = normalize_ado_audit_record(audit)

    assert event.event_type == "repo.deleted"
    assert event.payload == {}


def test_normalize_default_branch_changed_without_previous_branch() -> None:
    audit = {
        "Id": "911fef54-3e24-4c7a-bdf0-84679380b4c7",
        "ActionId": "Git.RepositoryDefaultBranchChanged",
        "ScopeId": "c638432a-7f35-450f-984f-372b9d46a376",
        "ScopeDisplayName": "torstencannell (Organization)",
        "ProjectId": "da9734d4-a91a-4f03-814b-ecc721fe24d1",
        "ProjectName": "snykDemoProject",
        "Timestamp": "2026-08-07T17:50:45.8246565Z",
        "Data": {
            "RepoId": "28b62628-73ec-4f6b-89cb-d5a023e9be23",
            "RepoName": "test-repo",
            "DefaultBranch": "refs/heads/main",
            "PreviousDefaultBranch": "",
        },
    }

    event = normalize_ado_audit_record(audit)

    assert event.event_type == "repo.default_branch_changed"
    assert event.payload == {"defaultBranch": "main"}


def test_normalize_unsupported_action_id() -> None:
    audit = {
        "Id": "x",
        "ActionId": "Git.RepositoryForked",
        "ScopeId": "org",
        "ScopeDisplayName": "org (Organization)",
        "ProjectId": "proj",
        "ProjectName": "proj-name",
        "Timestamp": "2026-08-05T18:00:00Z",
        "Data": {"RepoId": "repo", "RepoName": "r.git"},
    }

    with pytest.raises(NormalizationError, match="unsupported audit ActionId"):
        normalize_ado_audit_record(audit)


def test_normalize_missing_scope_id() -> None:
    audit = {
        "Id": "x",
        "ActionId": "Git.RepositoryDeleted",
        "ScopeDisplayName": "org (Organization)",
        "ProjectId": "proj",
        "ProjectName": "proj-name",
        "Timestamp": "2026-08-05T18:00:00Z",
        "Data": {"RepoId": "repo", "RepoName": "r.git"},
    }

    with pytest.raises(NormalizationError, match="ScopeId"):
        normalize_ado_audit_record(audit)
