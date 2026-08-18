"""Tests for ignore-policy lifecycle handling."""

from datetime import datetime, timezone
from unittest.mock import MagicMock

from config.ignored_repos import parse_ignore_policy_document
from config.scope_mapping import AdoScopeEntry, ResolvedScopeMapping, ScopeMappingSettings
from config.snyk_settings import SnykSettings, TargetRemovalSettings
from sync_state.entities import RepositoryState
from worker.ignore_policy import IgnorePolicyState
from worker.lifecycle import WorkerSyncDependencies, process_normalized_event
from worker.normalize import AdoScope, NormalizedEvent, RepositoryRef


def _policy_state() -> IgnorePolicyState:
    state = IgnorePolicyState()
    state.policy = parse_ignore_policy_document(
        {
            "repos": [{"source": "azure-repos", "owner": "proj", "name": "ignored-repo"}],
            "patterns": [{"id": "Disabled", "filterType": "prefix", "patterns": ["disabled-"]}],
        },
    )
    return state


def _deps(
    *,
    sync_state: MagicMock | None = None,
    snyk: MagicMock | None = None,
) -> WorkerSyncDependencies:
    return WorkerSyncDependencies(
        sync_state=sync_state or MagicMock(),
        snyk=snyk or MagicMock(),
        ado=MagicMock(),
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
        ignore_policy_state=_policy_state(),
    )


def _event(
    *,
    event_type: str = "repo.created",
    repo_name: str = "ignored-repo",
    payload: dict[str, str] | None = None,
) -> NormalizedEvent:
    return NormalizedEvent(
        source="ado",
        event_id="evt-ignore",
        event_type=event_type,  # type: ignore[arg-type]
        scope_id="scope",
        repository_id="repo",
        occurred_at=datetime(2026, 8, 14, tzinfo=timezone.utc),
        repository=RepositoryRef(name=repo_name),
        ado=AdoScope(
            org_id="org",
            org_display_name="org",
            project_id="scope",
            project_name="proj",
        ),
        payload=payload or {},
    )


def test_repo_created_skips_import_when_ignored() -> None:
    sync_state = MagicMock()
    sync_state.get_repository.return_value = None
    snyk = MagicMock()
    deps = _deps(sync_state=sync_state, snyk=snyk)

    outcome = process_normalized_event(
        _event(),
        ResolvedScopeMapping(snyk_org_id="org-1", resolution="mapped"),
        deps=deps,
    )

    snyk.start_import.assert_not_called()
    sync_state.upsert_repository.assert_not_called()
    assert outcome.skip_reason == "ignored"


def test_rename_into_ignore_removes_target_without_import() -> None:
    sync_state = MagicMock()
    sync_state.get_repository.return_value = RepositoryState(
        repo_name="old-name",
        snyk_target_id="target-1",
        default_branch="main",
        status="active",
        desired_state_hash="hash",
        last_event_id="evt-old",
        tag_applied=False,
        import_job_id="job-1",
        import_status="complete",
        owner_name="proj",
    )
    snyk = MagicMock()
    deps = _deps(sync_state=sync_state, snyk=snyk)

    outcome = process_normalized_event(
        _event(
            event_type="repo.renamed",
            repo_name="disabled-tool",
            payload={"previousRepoName": "old-name"},
        ),
        ResolvedScopeMapping(snyk_org_id="org-1", resolution="mapped"),
        deps=deps,
    )

    snyk.start_import.assert_not_called()
    snyk.deactivate_all_projects_for_target.assert_called_once_with("org-1", "target-1")
    sync_state.upsert_repository.assert_called_once()
    saved = sync_state.upsert_repository.call_args.args[0]
    assert saved.status == "inactive"
    assert outcome.skip_reason == "ignored"
