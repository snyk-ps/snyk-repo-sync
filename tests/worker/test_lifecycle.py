"""Tests for ADO lifecycle sync orchestration."""

import threading
import time
from dataclasses import replace
from datetime import UTC, datetime
from unittest.mock import MagicMock

from config.scope_mapping import (
    AdoScopeEntry,
    ResolvedScopeMapping,
    ScopeMappingSettings,
    parse_scope_mapping,
)
from config.snyk_settings import SnykSettings, TargetRemovalSettings
from snyk.client import ImportJobStatus
from sync_state.entities import RepositoryState
from worker.lifecycle import (
    WorkerSyncDependencies,
    process_import_poll,
    process_normalized_event,
)
from worker.normalize import AdoScope, GitHubScope, NormalizedEvent, RepositoryRef


def _deps(
    *,
    sync_state: MagicMock | None = None,
    snyk: MagicMock | None = None,
    ado: MagicMock | None = None,
) -> WorkerSyncDependencies:
    ado_client = ado or MagicMock()
    ado_client.get_repository_default_branch.return_value = "master"
    return WorkerSyncDependencies(
        sync_state=sync_state or MagicMock(),
        snyk=snyk or MagicMock(),
        ado=ado_client,
        integration_resolver=MagicMock(),
        scope_mapping=ScopeMappingSettings(
            default_snyk_org_id=None,
            ado_by_project_name={
                "proj": AdoScopeEntry(
                    snyk_org_id="org-1",
                    integration_type="azure-repos",
                    source="ado",
                    snyk_integration_id="integration-1",
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
                on_ignore="deactivate",
            ),
        ),
    )


def _created_event(*, with_default_branch: bool = False) -> NormalizedEvent:
    payload = {"defaultBranch": "main"} if with_default_branch else {}
    return NormalizedEvent(
        source="ado",
        event_id="evt-1",
        event_type="repo.created",
        scope_id="scope",
        repository_id="repo",
        occurred_at=datetime(2026, 8, 9, tzinfo=UTC),
        repository=RepositoryRef(name="demo"),
        ado=AdoScope(
            org_id="org",
            org_display_name="org",
            project_id="scope",
            project_name="proj",
        ),
        payload=payload,
    )


def _github_created_event() -> NormalizedEvent:
    return NormalizedEvent(
        source="github",
        event_id="github-event-1",
        event_type="repo.created",
        scope_id="contoso",
        repository_id="github-repo",
        occurred_at=datetime(2026, 10, 21, tzinfo=UTC),
        repository=RepositoryRef(name="demo"),
        github=GitHubScope(org_login="contoso"),
        payload={"defaultBranch": "main"},
    )


def test_repo_created_starts_import_and_schedules_poll() -> None:
    sync_state = MagicMock()
    sync_state.get_repository.return_value = None
    sync_state.count_pending_imports.return_value = 0
    snyk = MagicMock()
    snyk.start_import.return_value = "job-1"
    deps = _deps(sync_state=sync_state, snyk=snyk)
    deps.integration_resolver.resolve.return_value = "integration-1"

    outcome = process_normalized_event(
        _created_event(),
        ResolvedScopeMapping(snyk_org_id="org-1", resolution="mapped"),
        deps=deps,
    )

    sync_state.upsert_repository.assert_called_once()
    saved_state = sync_state.upsert_repository.call_args.args[0]
    assert saved_state.import_status == "pending"
    assert saved_state.import_job_id == "job-1"
    assert saved_state.default_branch == "master"
    import_target = snyk.start_import.call_args.args[2]
    assert import_target.branch == "master"
    deps.ado.get_repository_default_branch.assert_called_once_with("repo")
    assert len(outcome.scheduled_followups) == 1
    assert outcome.scheduled_followups[0].body["syncPhase"] == "import_poll"


def test_duplicate_pending_event_reschedules_missing_import_poll() -> None:
    sync_state = MagicMock()
    sync_state.get_repository.return_value = RepositoryState(
        repo_name="demo",
        snyk_target_id="",
        default_branch="main",
        status="pending",
        desired_state_hash="hash",
        last_event_id="evt-1",
        tag_applied=False,
        import_job_id="job-1",
        import_status="pending",
    )
    deps = _deps(sync_state=sync_state)

    outcome = process_normalized_event(
        _created_event(with_default_branch=True),
        ResolvedScopeMapping(snyk_org_id="org-1", resolution="mapped"),
        deps=deps,
    )

    assert outcome.skip_reason == "duplicate_event_pending_import"
    assert len(outcome.scheduled_followups) == 1
    assert outcome.scheduled_followups[0].body["importJobId"] == "job-1"
    deps.snyk.start_import.assert_not_called()


def test_concurrent_events_respect_pending_import_limit() -> None:
    saved_states: list[RepositoryState] = []
    sync_state = MagicMock()
    sync_state.get_repository.return_value = None
    sync_state.count_pending_imports.side_effect = lambda: len(saved_states)
    sync_state.upsert_repository.side_effect = (
        lambda state, **_kwargs: saved_states.append(state)
    )
    snyk = MagicMock()

    def start_import(*_args) -> str:
        time.sleep(0.02)
        return "job-1"

    snyk.start_import.side_effect = start_import
    deps = replace(
        _deps(sync_state=sync_state, snyk=snyk),
        snyk_settings=SnykSettings(
            max_concurrent_pending_imports=1,
            target_removal=TargetRemovalSettings(
                on_rename="deactivate",
                on_default_branch_change="deactivate",
                on_repo_delete="deactivate",
                on_ignore="deactivate",
            ),
        ),
    )
    deps.integration_resolver.resolve.return_value = "integration-1"
    barrier = threading.Barrier(2)
    outcomes = []

    def process(event: NormalizedEvent) -> None:
        barrier.wait()
        outcomes.append(
            process_normalized_event(
                event,
                ResolvedScopeMapping(snyk_org_id="org-1", resolution="mapped"),
                deps=deps,
            )
        )

    threads = [
        threading.Thread(
            target=process,
            args=(
                replace(
                    _created_event(with_default_branch=True),
                    event_id=f"evt-{index}",
                    repository_id=f"repo-{index}",
                ),
            ),
        )
        for index in range(2)
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    phases = sorted(
        outcome.scheduled_followups[0].body["syncPhase"] for outcome in outcomes
    )
    assert phases == ["import_poll", "lifecycle_deferred"]
    assert snyk.start_import.call_count == 1


def test_github_cloud_app_import_uses_resolved_integration_id() -> None:
    sync_state = MagicMock()
    sync_state.get_repository.return_value = None
    sync_state.count_pending_imports.return_value = 0
    snyk = MagicMock()
    snyk.start_import.return_value = "job-1"
    deps = replace(
        _deps(sync_state=sync_state, snyk=snyk),
        ado=None,
        scope_mapping=parse_scope_mapping(
            {
                "github-cloud-app": [
                    {"orgName": "contoso", "snykOrgId": "org-1"},
                ],
            },
        ),
    )
    deps.integration_resolver.resolve.return_value = "github-app-integration"

    process_normalized_event(
        _github_created_event(),
        ResolvedScopeMapping(snyk_org_id="org-1", resolution="mapped"),
        deps=deps,
    )

    deps.integration_resolver.resolve.assert_called_once_with(
        org_id="org-1",
        integration_type="github-cloud-app",
        configured_integration_id=None,
    )
    assert snyk.start_import.call_args.args[1] == "github-app-integration"
    assert snyk.start_import.call_args.args[2].branch == "main"


def test_repo_created_with_explicit_default_branch_stores_branch_in_state() -> None:
    sync_state = MagicMock()
    sync_state.get_repository.return_value = None
    sync_state.count_pending_imports.return_value = 0
    snyk = MagicMock()
    snyk.start_import.return_value = "job-1"
    ado = MagicMock()
    deps = _deps(sync_state=sync_state, snyk=snyk, ado=ado)
    deps.integration_resolver.resolve.return_value = "integration-1"

    process_normalized_event(
        _created_event(with_default_branch=True),
        ResolvedScopeMapping(snyk_org_id="org-1", resolution="mapped"),
        deps=deps,
    )

    saved_state = sync_state.upsert_repository.call_args.args[0]
    assert saved_state.default_branch == "main"
    import_target = snyk.start_import.call_args.args[2]
    assert import_target.branch == "main"
    ado.get_repository_default_branch.assert_not_called()


def test_import_poll_completes_and_retains_job_id() -> None:
    sync_state = MagicMock()
    sync_state.get_repository.return_value = RepositoryState(
        repo_name="demo",
        snyk_target_id="",
        default_branch="main",
        status="pending",
        desired_state_hash="hash",
        last_event_id="evt-1",
        tag_applied=False,
        import_job_id="job-1",
        import_status="pending",
    )
    snyk = MagicMock()
    snyk.get_import_job.return_value = ImportJobStatus(
        job_id="job-1",
        state="complete",
        target_id="",
    )
    snyk.find_target_id.return_value = "target-1"
    deps = _deps(sync_state=sync_state, snyk=snyk)
    deps.integration_resolver.resolve.return_value = "integration-1"

    outcome = process_import_poll(
        source="ado",
        scope_id="scope",
        repository_id="repo",
        source_event_id="evt-1",
        import_job_id="job-1",
        retry_count=0,
        scope_lookup_key="proj",
        deps=deps,
    )

    final_state = sync_state.upsert_repository.call_args.args[0]
    assert final_state.import_status == "complete"
    assert final_state.import_job_id == "job-1"
    assert final_state.snyk_target_id == "target-1"
    assert final_state.default_branch == "main"
    assert final_state.tag_applied is False
    snyk.find_target_id.assert_called_once()
    assert outcome.scheduled_followups == ()


def test_github_server_app_import_poll_filters_target_lookup() -> None:
    sync_state = MagicMock()
    sync_state.get_repository.return_value = RepositoryState(
        repo_name="demo",
        snyk_target_id="",
        default_branch="main",
        status="pending",
        desired_state_hash="hash",
        last_event_id="github-event-1",
        tag_applied=False,
        import_job_id="job-1",
        import_status="pending",
        owner_name="contoso",
    )
    snyk = MagicMock()
    snyk.get_import_job.return_value = ImportJobStatus(
        job_id="job-1",
        state="complete",
        target_id="",
    )
    snyk.find_target_id.return_value = "target-1"
    deps = replace(
        _deps(sync_state=sync_state, snyk=snyk),
        ado=None,
        scope_mapping=parse_scope_mapping(
            {
                "github-server-app": [
                    {"orgName": "contoso", "snykOrgId": "org-1"},
                ],
            },
        ),
    )
    deps.integration_resolver.resolve.return_value = "github-app-integration"

    process_import_poll(
        source="github",
        scope_id="contoso",
        repository_id="github-repo",
        source_event_id="github-event-1",
        import_job_id="job-1",
        retry_count=0,
        scope_lookup_key="contoso",
        deps=deps,
    )

    snyk.find_target_id.assert_called_once_with(
        "org-1",
        owner="contoso",
        repo_name="demo",
        branch="main",
        source_type="github-server-app",
    )


def test_import_poll_uses_stored_org_when_static_mapping_misses() -> None:
    sync_state = MagicMock()
    sync_state.get_repository.return_value = RepositoryState(
        repo_name="demo",
        snyk_target_id="",
        default_branch="main",
        status="pending",
        desired_state_hash="hash",
        last_event_id="evt-1",
        tag_applied=False,
        import_job_id="job-1",
        import_status="pending",
        snyk_org_id="stored-org",
        snyk_integration_type="github-enterprise",
    )
    snyk = MagicMock()
    snyk.get_import_job.return_value = ImportJobStatus(
        job_id="job-1",
        state="complete",
        target_id="",
    )
    snyk.find_target_id.return_value = "target-1"
    deps = replace(
        _deps(sync_state=sync_state, snyk=snyk),
        scope_mapping=ScopeMappingSettings(
            default_snyk_org_id="default-org",
            ado_by_project_name={},
            github_by_org_name={},
            configured_github_integration_types=frozenset({"github"}),
        ),
    )
    deps.integration_resolver.resolve.return_value = "integration-stored"

    process_import_poll(
        source="github",
        scope_id="contoso",
        repository_id="repo",
        source_event_id="evt-1",
        import_job_id="job-1",
        retry_count=0,
        scope_lookup_key="contoso",
        deps=deps,
    )

    snyk.get_import_job.assert_called_once_with("stored-org", "integration-stored", "job-1")
    deps.integration_resolver.resolve.assert_called_once_with(
        org_id="stored-org",
        integration_type="github-enterprise",
        configured_integration_id=None,
    )
    snyk.list_group_orgs.assert_not_called()
    saved = sync_state.upsert_repository.call_args.args[0]
    assert saved.snyk_org_id == "stored-org"
    assert saved.snyk_integration_type == "github-enterprise"


def test_repo_deleted_marks_inactive() -> None:
    sync_state = MagicMock()
    sync_state.get_repository.return_value = RepositoryState(
        repo_name="demo",
        snyk_target_id="target-1",
        default_branch="main",
        status="active",
        desired_state_hash="hash",
        last_event_id="evt-old",
        tag_applied=False,
        import_job_id="job-old",
        import_status="complete",
    )
    deps = _deps(sync_state=sync_state)

    event = _created_event()
    event = NormalizedEvent(
        source=event.source,
        event_id="evt-delete",
        event_type="repo.deleted",
        scope_id=event.scope_id,
        repository_id=event.repository_id,
        occurred_at=event.occurred_at,
        repository=event.repository,
        ado=event.ado,
        payload={},
    )

    outcome = process_normalized_event(
        event,
        ResolvedScopeMapping(snyk_org_id="org-1", resolution="mapped"),
        deps=deps,
    )

    saved_state = sync_state.upsert_repository.call_args.args[0]
    assert saved_state.status == "inactive"
    deps.snyk.deactivate_all_projects_for_target.assert_called_once_with("org-1", "target-1")
    assert outcome.scheduled_followups == ()


def test_import_poll_dead_letters_after_max_retries() -> None:
    sync_state = MagicMock()
    deps = _deps(sync_state=sync_state)
    deps.integration_resolver.resolve.return_value = "integration-1"

    outcome = process_import_poll(
        source="ado",
        scope_id="scope",
        repository_id="repo",
        source_event_id="evt-1",
        import_job_id="job-1",
        retry_count=5,
        scope_lookup_key="proj",
        deps=deps,
    )

    assert outcome.settlement == "dead_letter"
    assert outcome.dead_letter_reason == "ImportJobFailed"


def test_pending_import_limit_defers_lifecycle() -> None:
    sync_state = MagicMock()
    sync_state.get_repository.return_value = None
    sync_state.count_pending_imports.return_value = 100
    deps = _deps(sync_state=sync_state)

    outcome = process_normalized_event(
        _created_event(with_default_branch=True),
        ResolvedScopeMapping(snyk_org_id="org-1", resolution="mapped"),
        deps=deps,
    )

    assert outcome.scheduled_followups[0].body["syncPhase"] == "lifecycle_deferred"
    deps.snyk.start_import.assert_not_called()
