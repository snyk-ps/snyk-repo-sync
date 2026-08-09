"""Tests for queue message handling."""

import json

from config.scope_mapping import (
    AdoScopeEntry,
    ResolvedScopeMapping,
    ScopeMappingSettings,
    UnmappedScope,
)
from worker.handler import handle_queue_message


def _ado_created_body(project_name: str = "proj") -> bytes:
    return json.dumps(
        {
            "subject": "AzureDevOps/Auditing",
            "eventType": "AzureDevOpsAuditEvent",
            "data": {
                "Id": "evt-1",
                "ActionId": "Git.RepositoryCreated",
                "ScopeId": "org",
                "ScopeDisplayName": "org",
                "ProjectId": "proj-id",
                "ProjectName": project_name,
                "Timestamp": "2026-08-07T17:50:45.8246565Z",
                "Data": {"RepoId": "repo", "RepoName": "demo"},
            },
        }
    ).encode("utf-8")


def test_handle_default_branch_changed_without_previous_branch_completes(caplog) -> None:
    body = json.dumps(
        {
            "id": "911fef54-3e24-4c7a-bdf0-84679380b4c7",
            "subject": "AzureDevOps/Auditing",
            "eventType": "AzureDevOpsAuditEvent",
            "data": {
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
            },
        }
    ).encode("utf-8")

    with caplog.at_level("INFO"):
        result = handle_queue_message(body)

    assert result.normalized is not None
    assert result.normalized.payload == {"defaultBranch": "main"}
    assert isinstance(result.scope_resolution, UnmappedScope)
    assert "no sync action needed" in caplog.text
    assert "Normalized ADO lifecycle event" not in caplog.text


def test_handle_ado_created_normalizes_and_returns_event() -> None:
    result = handle_queue_message(_ado_created_body())

    assert result.normalized is not None
    assert result.normalized.event_type == "repo.created"
    assert isinstance(result.scope_resolution, UnmappedScope)


def test_handle_ado_created_resolves_mapped_scope(caplog) -> None:
    mapping = ScopeMappingSettings(
        default_snyk_org_id=None,
        ado_by_project_name={
            "proj": AdoScopeEntry(
                project_name="proj",
                snyk_org_id="mapped-org",
            ),
        },
        github_by_org_name={},
    )

    with caplog.at_level("INFO"):
        result = handle_queue_message(_ado_created_body(), scope_mapping=mapping)

    assert isinstance(result.scope_resolution, ResolvedScopeMapping)
    assert result.scope_resolution.snyk_org_id == "mapped-org"
    assert "Resolved scope mapping" in caplog.text
    assert "mapped-org" in caplog.text


def test_handle_ado_created_uses_default_org(caplog) -> None:
    mapping = ScopeMappingSettings(
        default_snyk_org_id="default-org",
        ado_by_project_name={},
        github_by_org_name={},
    )

    with caplog.at_level("INFO"):
        result = handle_queue_message(_ado_created_body("other-project"), scope_mapping=mapping)

    assert isinstance(result.scope_resolution, ResolvedScopeMapping)
    assert result.scope_resolution.resolution == "default"
    assert result.scope_resolution.snyk_org_id == "default-org"
    assert "default-org" in caplog.text


def test_handle_ado_created_logs_unmapped_scope(caplog) -> None:
    with caplog.at_level("WARNING"):
        result = handle_queue_message(_ado_created_body("missing-project"))

    assert isinstance(result.scope_resolution, UnmappedScope)
    assert "Unmapped scope" in caplog.text


def test_handle_github_message_skips_scope_resolution() -> None:
    body = json.dumps(
        {
            "action": "created",
            "repository": {
                "id": 1,
                "name": "demo",
                "full_name": "org/demo",
            },
        }
    ).encode("utf-8")

    result = handle_queue_message(body)

    assert result.normalized is None
    assert result.scope_resolution is None
