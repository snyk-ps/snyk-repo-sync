"""Tests for queue message handling."""

import json
from unittest.mock import MagicMock

from config.scope_mapping import (
    AdoScopeEntry,
    ResolvedScopeMapping,
    ScopeMappingSettings,
    UnmappedScope,
)
from config.snyk_settings import SnykSettings, TargetRemovalSettings
from worker.handler import handle_queue_message
from worker.lifecycle import WorkerSyncDependencies


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
                snyk_org_id="mapped-org",
                integration_type="azure-repos",
                source="ado",
            ),
        },
        github_by_org_name={},
        configured_github_integration_types=frozenset(),
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
        configured_github_integration_types=frozenset(),
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


def _sync_deps() -> WorkerSyncDependencies:
    sync_state = MagicMock()
    sync_state.get_repository.return_value = None
    sync_state.count_pending_imports.return_value = 0
    snyk = MagicMock()
    snyk.start_import.return_value = "job-1"
    integration_resolver = MagicMock()
    integration_resolver.resolve.return_value = "integration-1"
    ado = MagicMock()
    return WorkerSyncDependencies(
        sync_state=sync_state,
        snyk=snyk,
        ado=ado,
        integration_resolver=integration_resolver,
        scope_mapping=ScopeMappingSettings(
            default_snyk_org_id=None,
            ado_by_project_name={
                "proj": AdoScopeEntry(
                    snyk_org_id="mapped-org",
                    integration_type="azure-repos",
                    source="ado",
                ),
            },
            github_by_org_name={},
            configured_github_integration_types=frozenset(),
        ),
        snyk_settings=SnykSettings(
            max_concurrent_pending_imports=100,
            target_removal=TargetRemovalSettings(
                on_rename="deactivate",
                on_default_branch_change="deactivate",
                on_repo_delete="deactivate",
            ),
        ),
    )


def test_handle_ado_created_with_sync_deps_schedules_import_poll() -> None:
    mapping = ScopeMappingSettings(
        default_snyk_org_id=None,
        ado_by_project_name={
            "proj": AdoScopeEntry(
                snyk_org_id="mapped-org",
                integration_type="azure-repos",
                source="ado",
            ),
        },
        github_by_org_name={},
        configured_github_integration_types=frozenset(),
    )
    result = handle_queue_message(
        _ado_created_body(),
        scope_mapping=mapping,
        sync_deps=_sync_deps(),
    )

    assert result.settlement == "complete"
    assert len(result.scheduled_followups) == 1
    assert result.scheduled_followups[0].body["syncPhase"] == "import_poll"
