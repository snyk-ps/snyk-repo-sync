"""Tests for queue message handling."""

import json

from worker.handler import handle_queue_message


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
    assert "no sync action needed" in caplog.text
    assert "Normalized ADO lifecycle event" not in caplog.text


def test_handle_ado_created_normalizes_and_returns_event() -> None:
    body = json.dumps(
        {
            "subject": "AzureDevOps/Auditing",
            "eventType": "AzureDevOpsAuditEvent",
            "data": {
                "Id": "evt-1",
                "ActionId": "Git.RepositoryCreated",
                "ScopeId": "org",
                "ScopeDisplayName": "org",
                "ProjectId": "proj",
                "ProjectName": "proj",
                "Timestamp": "2026-08-07T17:50:45.8246565Z",
                "Data": {"RepoId": "repo", "RepoName": "demo"},
            },
        }
    ).encode("utf-8")

    result = handle_queue_message(body)

    assert result.normalized is not None
    assert result.normalized.event_type == "repo.created"
