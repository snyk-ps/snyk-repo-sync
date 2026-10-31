"""Tests for v1 project-ignore copy and source retirement."""

from dataclasses import replace
from unittest.mock import MagicMock

from config.snyk_settings import SnykSettings, TargetRemovalSettings
from snyk.client import ProjectIgnore, SnykApiError, SnykProject
from sync_state.entities import RepositoryState
from worker.ignore_migration import copy_v1_project_ignores, projects_for_reference
from worker.lifecycle import WorkerSyncDependencies, process_ignore_migration, process_import_poll


def _project(
    project_id: str,
    *,
    project_type: str = "npm",
    target_file: str = "package.json",
    target_reference: str = "main",
    deactivated: bool = False,
) -> SnykProject:
    return SnykProject(
        id=project_id,
        project_type=project_type,
        target_file=target_file,
        target_reference=target_reference,
        deactivated=deactivated,
    )


def _ignore(issue_id: str = "SNYK-JS-1", path: str = "*") -> ProjectIgnore:
    return ProjectIgnore(
        issue_id=issue_id,
        path=path,
        reason="secret-ignore-text",
        reason_type="wont-fix",
        disregard_if_fixable=True,
        expires="2026-12-01T00:00:00.000Z",
    )


def _state(**overrides: object) -> RepositoryState:
    state = RepositoryState(
        repo_name="demo",
        snyk_target_id="target-new",
        default_branch="main",
        status="active",
        desired_state_hash="hash",
        last_event_id="evt-1",
        tag_applied=False,
        import_job_id="job-1",
        import_status="complete",
        snyk_org_id="org-1",
        snyk_integration_type="github",
        ignore_migration_kind="rename",
        ignore_migration_status="pending",
        ignore_source_org_id="org-1",
        ignore_source_target_id="target-old",
        ignore_source_target_reference="main",
    )
    return replace(state, **overrides)  # type: ignore[arg-type]


def _deps(
    *,
    state: RepositoryState | None,
    snyk: MagicMock | None = None,
    migrate_ignores: bool = True,
    on_rename: str = "deactivate",
    on_default_branch_change: str = "deactivate",
) -> WorkerSyncDependencies:
    sync_state = MagicMock()
    sync_state.get_repository.return_value = state
    client = snyk or MagicMock()
    return WorkerSyncDependencies(
        sync_state=sync_state,
        snyk=client,
        ado=None,
        integration_resolver=MagicMock(),
        scope_mapping=MagicMock(),
        snyk_settings=SnykSettings(
            max_concurrent_pending_imports=100,
            target_removal=TargetRemovalSettings(
                on_rename=on_rename,  # type: ignore[arg-type]
                on_default_branch_change=on_default_branch_change,  # type: ignore[arg-type]
                on_repo_delete="deactivate",
                on_ignore="deactivate",
            ),
            migrate_ignores=migrate_ignores,
        ),
    )


def _run(deps: WorkerSyncDependencies, *, retry_count: int = 0, extracted: str | None = None):
    return process_ignore_migration(
        source="github",
        scope_id="scope",
        repository_id="repo",
        source_event_id="evt-1",
        retry_count=retry_count,
        scope_lookup_key="sample-org",
        extracted_property_value=extracted,
        deps=deps,
    )


def test_copy_sends_v1_fields_except_actor_and_created() -> None:
    snyk = MagicMock()
    snyk.list_project_ignores.side_effect = [[_ignore()], []]
    source = _project("src", target_reference="develop")
    destination = _project("dst", target_reference="main")

    outcome = copy_v1_project_ignores(
        snyk,
        source_org_id="org-src",
        source_projects=[source],
        destination_org_id="org-dst",
        destination_projects=[destination],
        import_branch="main",
    )

    assert outcome == "succeeded"
    snyk.add_missing_project_ignores.assert_called_once_with("org-dst", "dst", [_ignore()])
    called = {call[0] for call in snyk.method_calls}
    assert "list_code_consistent_ignores" not in called
    assert "create_code_consistent_ignore" not in called


def test_configured_skip_does_not_call_ignore_apis_and_still_retires(caplog) -> None:
    snyk = MagicMock()
    deps = _deps(state=_state(), snyk=snyk, migrate_ignores=False)

    with caplog.at_level("INFO"):
        outcome = _run(deps)

    assert outcome.settlement == "complete"
    snyk.list_project_ignores.assert_not_called()
    snyk.add_missing_project_ignores.assert_not_called()
    snyk.create_project_ignore.assert_not_called()
    snyk.deactivate_all_projects_for_target.assert_called_once_with("org-1", "target-old")
    saved = deps.sync_state.upsert_repository.call_args_list[-1].args[0]
    assert saved.ignore_migration_kind == ""
    assert saved.ignore_source_target_id == ""
    assert "outcome=skipped" in caplog.text
    assert "ignore_migration_kind=rename" in caplog.text
    assert "secret-ignore-text" not in caplog.text


def test_rename_copies_then_deletes_previous_target(caplog) -> None:
    snyk = MagicMock()
    snyk.list_projects_for_target.side_effect = [
        [_project("src", target_reference="develop")],
        [_project("dst")],
    ]
    snyk.list_project_ignores.side_effect = [[_ignore()], []]
    deps = _deps(state=_state(), snyk=snyk, on_rename="delete")

    with caplog.at_level("INFO"):
        _run(deps)

    snyk.add_missing_project_ignores.assert_called_once()
    snyk.delete_snyk_target.assert_called_once_with("org-1", "target-old")
    snyk.deactivate_all_projects_for_target.assert_not_called()
    assert "outcome=succeeded" in caplog.text
    assert "secret-ignore-text" not in caplog.text


def test_copy_failure_does_not_retire_and_reschedules(caplog) -> None:
    snyk = MagicMock()
    snyk.list_projects_for_target.return_value = [_project("src")]
    snyk.list_project_ignores.side_effect = SnykApiError(
        "secret-ignore-text leaked",
        status_code=500,
    )
    deps = _deps(state=_state(), snyk=snyk)

    with caplog.at_level("ERROR"):
        outcome = _run(deps)

    assert outcome.scheduled_followups[0].body["syncPhase"] == "ignore_migration"
    assert outcome.scheduled_followups[0].body["retryCount"] == 1
    snyk.deactivate_all_projects_for_target.assert_not_called()
    snyk.delete_snyk_target.assert_not_called()
    assert "outcome=failed" in caplog.text
    assert "reason=snyk_api_status_500" in caplog.text
    assert "secret-ignore-text" not in caplog.text


def test_nothing_to_copy_still_retires() -> None:
    snyk = MagicMock()
    snyk.list_projects_for_target.return_value = [_project("src")]
    snyk.list_project_ignores.return_value = []
    deps = _deps(state=_state(), snyk=snyk)

    outcome = _run(deps)

    assert outcome.settlement == "complete"
    snyk.deactivate_all_projects_for_target.assert_called_once_with("org-1", "target-old")
    saved = deps.sync_state.upsert_repository.call_args_list[-1].args[0]
    assert saved.ignore_migration_status == ""


def test_retry_limit_dead_letters_without_retirement() -> None:
    snyk = MagicMock()
    deps = _deps(state=_state(), snyk=snyk)

    outcome = _run(deps, retry_count=5)

    assert outcome.settlement == "dead_letter"
    assert outcome.dead_letter_reason == "IgnoreMigrationFailed"
    snyk.deactivate_all_projects_for_target.assert_not_called()
    snyk.delete_snyk_target.assert_not_called()
    snyk.list_project_ignores.assert_not_called()


def test_default_branch_source_list_includes_deactivated_previous_branch() -> None:
    previous = _project("old", target_reference="develop", deactivated=True)
    still_active = _project("old-active", target_reference="develop")
    other_branch = _project("new", target_reference="main", deactivated=True)

    selected = projects_for_reference(
        [previous, still_active, other_branch],
        target_reference="develop",
        include_deactivated=True,
    )

    assert [project.id for project in selected] == ["old", "old-active"]


def test_destination_list_excludes_deactivated_projects() -> None:
    active = _project("new", target_reference="main")
    deactivated = _project("dead", target_reference="main", deactivated=True)
    previous = _project("old", target_reference="develop")

    selected = projects_for_reference(
        [active, deactivated, previous],
        target_reference="main",
    )

    assert [project.id for project in selected] == ["new"]


def test_deactivated_previous_branch_ignores_are_copied() -> None:
    snyk = MagicMock()
    previous = _project("old", target_reference="develop", deactivated=True)
    current = _project("new", target_reference="main")
    snyk.list_projects_for_target.side_effect = [
        [previous, current],
        [previous, current],
        [previous, current],
    ]
    snyk.list_project_ignores.return_value = [_ignore()]
    deps = _deps(
        state=_state(
            ignore_migration_kind="default_branch",
            snyk_target_id="target-1",
            ignore_source_target_id="target-1",
            ignore_source_target_reference="develop",
            default_branch="main",
        ),
        snyk=snyk,
    )

    outcome = _run(deps)

    assert outcome.settlement == "complete"
    assert [call.args for call in snyk.list_project_ignores.call_args_list] == [("org-1", "old")]
    snyk.add_missing_project_ignores.assert_called_once_with("org-1", "new", [_ignore()])


def test_deactivated_new_branch_destination_is_not_copied() -> None:
    snyk = MagicMock()
    previous = _project("old", target_reference="develop", deactivated=True)
    dead = _project("dead", target_reference="main", deactivated=True)
    snyk.list_projects_for_target.side_effect = [
        [previous, dead],
        [previous, dead],
    ]
    snyk.list_project_ignores.return_value = [_ignore()]
    deps = _deps(
        state=_state(
            ignore_migration_kind="default_branch",
            snyk_target_id="target-1",
            ignore_source_target_id="target-1",
            ignore_source_target_reference="develop",
            default_branch="main",
        ),
        snyk=snyk,
    )

    outcome = _run(deps)

    assert outcome.scheduled_followups
    assert [call.args for call in snyk.list_project_ignores.call_args_list] == [("org-1", "old")]
    snyk.add_missing_project_ignores.assert_not_called()
    snyk.deactivate_project.assert_not_called()
    snyk.delete_project.assert_not_called()


def test_deactivated_rename_source_produces_no_ignores_request() -> None:
    snyk = MagicMock()
    deactivated = _project("old", deactivated=True)
    active = _project("src")
    destination = _project("dst")
    snyk.list_projects_for_target.side_effect = [
        [deactivated, active],
        [destination],
    ]
    snyk.list_project_ignores.return_value = [_ignore()]
    deps = _deps(state=_state(), snyk=snyk)

    outcome = _run(deps)

    assert outcome.settlement == "complete"
    assert [call.args for call in snyk.list_project_ignores.call_args_list] == [("org-1", "src")]
    snyk.add_missing_project_ignores.assert_called_once_with("org-1", "dst", [_ignore()])


def test_default_branch_deletes_only_previous_projects() -> None:
    snyk = MagicMock()
    previous = _project("old", target_reference="develop")
    current = _project("new", target_reference="main")
    snyk.list_projects_for_target.side_effect = [
        [previous, current],
        [previous, current],
        [previous, current],
    ]
    snyk.list_project_ignores.side_effect = [[_ignore()], []]
    deps = _deps(
        state=_state(
            ignore_migration_kind="default_branch",
            snyk_target_id="target-1",
            ignore_source_target_id="target-1",
            ignore_source_target_reference="develop",
            default_branch="main",
        ),
        snyk=snyk,
        on_default_branch_change="delete",
    )

    _run(deps)

    snyk.delete_project.assert_called_once_with("org-1", "old")
    snyk.delete_snyk_target.assert_not_called()
    snyk.add_missing_project_ignores.assert_called_once()
    copied_to = snyk.add_missing_project_ignores.call_args.args[1]
    assert copied_to == "new"


def test_default_branch_deactivate_leaves_target(caplog) -> None:
    snyk = MagicMock()
    previous = _project("old", target_reference="develop")
    current = _project("new", target_reference="main")
    snyk.list_projects_for_target.side_effect = [
        [previous],
        [current],
        [previous, current],
    ]
    snyk.list_project_ignores.side_effect = [[_ignore()], []]
    deps = _deps(
        state=_state(
            ignore_migration_kind="default_branch",
            snyk_target_id="target-1",
            ignore_source_target_id="target-1",
            ignore_source_target_reference="develop",
        ),
        snyk=snyk,
    )

    with caplog.at_level("INFO"):
        _run(deps)

    snyk.deactivate_project.assert_called_once_with("org-1", "old")
    snyk.delete_snyk_target.assert_not_called()
    snyk.deactivate_all_projects_for_target.assert_not_called()
    assert "outcome=succeeded" in caplog.text


def test_updated_copies_from_ado_target_and_does_not_deactivate(caplog) -> None:
    snyk = MagicMock()
    snyk.find_target_id.return_value = "ado-target"
    snyk.list_projects_for_target.side_effect = [
        [_project("ado", target_reference="main")],
        [_project("gh", target_reference="main")],
    ]
    snyk.list_project_ignores.side_effect = [[_ignore()], []]
    deps = _deps(
        state=_state(
            ignore_migration_kind="updated",
            ignore_source_target_id="",
            ignore_source_org_id="",
            ignore_source_target_reference="",
            repo_name="sample-repo",
            default_branch="main",
        ),
        snyk=snyk,
    )

    with caplog.at_level("INFO"):
        _run(deps, extracted="sample-project")

    snyk.find_target_id.assert_called_once_with(
        "org-1",
        owner="sample-project",
        repo_name="sample-repo",
        branch="main",
        source_type="azure-repos",
    )
    snyk.deactivate_all_projects_for_target.assert_not_called()
    snyk.deactivate_project.assert_not_called()
    snyk.delete_snyk_target.assert_not_called()
    snyk.delete_project.assert_not_called()
    assert "outcome=succeeded" in caplog.text
    saved = deps.sync_state.upsert_repository.call_args_list[-1].args[0]
    assert saved.ignore_migration_kind == ""
    assert saved.ignore_source_target_id == ""


def test_updated_missing_ado_target_skips(caplog) -> None:
    snyk = MagicMock()
    snyk.find_target_id.return_value = None
    deps = _deps(
        state=_state(
            ignore_migration_kind="updated",
            ignore_source_target_id="",
            repo_name="sample-repo",
        ),
        snyk=snyk,
    )

    with caplog.at_level("INFO"):
        outcome = _run(deps, extracted="sample-project")

    assert outcome.settlement == "complete"
    snyk.list_project_ignores.assert_not_called()
    snyk.deactivate_project.assert_not_called()
    assert "outcome=skipped" in caplog.text


def test_unmatched_ignores_do_not_retire() -> None:
    snyk = MagicMock()
    snyk.list_projects_for_target.side_effect = [
        [_project("src", target_file="package.json")],
        [_project("dst", project_type="pip", target_file="requirements.txt")],
    ]
    snyk.list_project_ignores.return_value = [_ignore()]
    deps = _deps(state=_state(), snyk=snyk)

    outcome = _run(deps)

    assert outcome.scheduled_followups
    snyk.deactivate_all_projects_for_target.assert_not_called()


def test_import_poll_schedules_ignore_migration_when_kind_is_pending() -> None:
    from snyk.client import ImportJobStatus

    sync_state = MagicMock()
    sync_state.get_repository.return_value = _state(
        import_status="pending",
        snyk_target_id="",
        ignore_migration_kind="rename",
        ignore_migration_status="pending",
        ignore_source_target_id="target-old",
    )
    snyk = MagicMock()
    snyk.get_import_job.return_value = ImportJobStatus(job_id="job-1", state="complete")
    snyk.find_target_id.return_value = "target-new"
    deps = _deps(state=None, snyk=snyk)
    deps = replace(deps, sync_state=sync_state)
    deps.integration_resolver.resolve.return_value = "integration-1"
    from config.scope_mapping import ScopeMappingSettings

    deps = replace(
        deps,
        scope_mapping=ScopeMappingSettings(
            default_snyk_org_id="org-1",
            ado_by_project_name={},
            github_by_org_name={},
            configured_github_integration_types=frozenset({"github"}),
        ),
    )

    outcome = process_import_poll(
        source="github",
        scope_id="scope",
        repository_id="repo",
        source_event_id="evt-1",
        import_job_id="job-1",
        retry_count=0,
        scope_lookup_key="sample-org",
        extracted_property_value="sample-project",
        deps=deps,
    )

    assert outcome.scheduled_followups[0].body["syncPhase"] == "ignore_migration"
    assert outcome.scheduled_followups[0].body["extractedPropertyValue"] == "sample-project"
    saved = sync_state.upsert_repository.call_args.args[0]
    assert saved.import_status == "complete"
    assert saved.snyk_target_id == "target-new"
    assert saved.ignore_migration_kind == "rename"
    assert saved.ignore_source_target_id == "target-old"
    snyk.deactivate_all_projects_for_target.assert_not_called()


def test_blank_org_updated_event_does_not_import_when_hash_matches() -> None:
    from datetime import UTC, datetime

    from config.scope_mapping import ResolvedScopeMapping
    from worker.idempotency import compute_desired_state_hash
    from worker.lifecycle import process_normalized_event
    from worker.normalize import GitHubScope, NormalizedEvent, RepositoryRef

    desired = compute_desired_state_hash(
        event_type="repo.created",
        repo_name="demo",
        default_branch="main",
        status="active",
    )
    sync_state = MagicMock()
    sync_state.get_repository.return_value = _state(
        desired_state_hash=desired,
        snyk_org_id=None,
        snyk_integration_type=None,
        ignore_migration_kind="",
        ignore_migration_status="",
        ignore_source_org_id="",
        ignore_source_target_id="",
        ignore_source_target_reference="",
    )
    snyk = MagicMock()
    deps = _deps(state=None, snyk=snyk)
    deps = replace(deps, sync_state=sync_state)
    event = NormalizedEvent(
        source="github",
        event_id="evt-new",
        event_type="repo.created",
        scope_id="scope",
        repository_id="repo",
        occurred_at=datetime(2026, 10, 30, tzinfo=UTC),
        repository=RepositoryRef(name="demo"),
        github=GitHubScope(org_login="sample-org"),
        payload={"defaultBranch": "main"},
        parsed_updated_import=True,
    )

    outcome = process_normalized_event(
        event,
        ResolvedScopeMapping(
            snyk_org_id="org-1",
            resolution="mapped",
            integration_type="github",
        ),
        deps=deps,
    )

    assert outcome.skip_reason == "desired_state_current"
    snyk.start_import.assert_not_called()
