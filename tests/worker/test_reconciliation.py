"""Tests for ignore-policy reconciliation."""

from unittest.mock import MagicMock

from config.ignored_repos import IgnoredReposSettings, parse_ignore_policy_document
from config.scope_mapping import AdoScopeEntry, ResolvedScopeMapping, ScopeMappingSettings
from config.snyk_settings import SnykSettings, TargetRemovalSettings
from sync_state.client import ActiveRepositoryRow
from sync_state.entities import RepositoryState
from worker.ignore_policy import IgnorePolicyState
from worker.lifecycle import WorkerSyncDependencies
from worker.reconciliation import run_reconciliation_cycle


def test_reconciliation_removes_stale_ignored_target(tmp_path) -> None:
    policy_path = tmp_path / "ignored-repos.yaml"
    policy_path.write_text(
        """
repos:
  - source: azure-repos
    owner: proj
    name: archived
""".strip(),
        encoding="utf-8",
    )
    policy_state = IgnorePolicyState()
    policy_state.policy = parse_ignore_policy_document(
        {"repos": [{"source": "azure-repos", "owner": "proj", "name": "archived"}]},
    )

    sync_state = MagicMock()
    sync_state.load_persisted_ignore_policy.return_value = policy_state.policy
    sync_state.list_active_repositories.return_value = [
        ActiveRepositoryRow(
            source="ado",
            scope_id="scope",
            repository_id="repo",
            state=RepositoryState(
                repo_name="archived",
                snyk_target_id="target-1",
                default_branch="main",
                status="active",
                desired_state_hash="hash",
                last_event_id="evt-1",
                tag_applied=False,
                import_job_id="job-1",
                import_status="complete",
                owner_name="proj",
            ),
        ),
    ]

    snyk = MagicMock()
    deps = WorkerSyncDependencies(
        sync_state=sync_state,
        snyk=snyk,
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
    )

    stats = run_reconciliation_cycle(
        settings=IgnoredReposSettings(policy_path=policy_path, reconciliation_interval_minutes=15),
        policy_state=policy_state,
        sync_state=sync_state,
        deps=deps,
    )

    assert stats.matched == 1
    assert stats.removed == 1
    snyk.deactivate_all_projects_for_target.assert_called_once_with("org-1", "target-1")
    sync_state.upsert_repository.assert_called_once()
