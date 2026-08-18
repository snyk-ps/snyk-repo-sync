"""End-to-end handler test for ADO create with mocked Snyk and sync state."""

import json
from unittest.mock import MagicMock

from config.scope_mapping import AdoScopeEntry, ScopeMappingSettings
from config.snyk_settings import SnykSettings, TargetRemovalSettings
from worker.handler import handle_queue_message
from worker.lifecycle import WorkerSyncDependencies


def test_ado_create_fixture_pending_then_complete_flow() -> None:
    sync_state = MagicMock()
    sync_state.get_repository.return_value = None
    sync_state.count_pending_imports.return_value = 0
    snyk = MagicMock()
    snyk.start_import.return_value = "job-1"
    integration_resolver = MagicMock()
    integration_resolver.resolve.return_value = "integration-1"
    ado = MagicMock()
    ado.get_repository_default_branch.return_value = "main"

    mapping = ScopeMappingSettings(
        default_snyk_org_id=None,
        ado_by_project_name={
            "proj": AdoScopeEntry(
                snyk_org_id="org-1",
                integration_type="azure-repos",
                source="ado",
            ),
        },
        github_by_org_name={},
        configured_github_integration_types=frozenset(),
    )
    deps = WorkerSyncDependencies(
        sync_state=sync_state,
        snyk=snyk,
        ado=ado,
        integration_resolver=integration_resolver,
        scope_mapping=mapping,
        snyk_settings=SnykSettings(
            max_concurrent_pending_imports=100,
            target_removal=TargetRemovalSettings(
                on_rename="deactivate",
                on_default_branch_change="deactivate",
                on_repo_delete="deactivate",
                on_ignore="deactivate",
            ),
        ),
    )

    body = json.dumps(
        {
            "subject": "AzureDevOps/Auditing",
            "eventType": "AzureDevOpsAuditEvent",
            "data": {
                "Id": "evt-1",
                "ActionId": "Git.RepositoryCreated",
                "ScopeId": "org",
                "ScopeDisplayName": "org",
                "ProjectId": "scope",
                "ProjectName": "proj",
                "Timestamp": "2026-08-07T17:50:45.8246565Z",
                "Data": {"RepoId": "repo", "RepoName": "demo", "DefaultBranch": "refs/heads/main"},
            },
        },
    ).encode("utf-8")

    create_result = handle_queue_message(body, scope_mapping=mapping, sync_deps=deps)
    assert create_result.scheduled_followups[0].body["importStatus"] == "pending"
    pending_state = sync_state.upsert_repository.call_args.args[0]
    assert pending_state.import_status == "pending"

    from snyk.client import ImportJobStatus
    from sync_state.entities import RepositoryState
    from worker.lifecycle import process_import_poll

    sync_state.get_repository.return_value = pending_state
    snyk.get_import_job.return_value = ImportJobStatus(
        job_id="job-1",
        state="complete",
        target_id="",
    )
    snyk.find_target_id.return_value = "target-1"
    poll_result = process_import_poll(
        source="ado",
        scope_id="scope",
        repository_id="repo",
        source_event_id="evt-1",
        import_job_id="job-1",
        retry_count=0,
        ado_project_name="proj",
        deps=deps,
    )

    final_state = sync_state.upsert_repository.call_args.args[0]
    assert isinstance(final_state, RepositoryState)
    assert final_state.import_status == "complete"
    assert final_state.import_job_id == "job-1"
    assert poll_result.scheduled_followups == ()
