"""Tests for lifecycle idempotency helpers."""

from sync_state.entities import RepositoryState
from worker.idempotency import (
    compute_desired_state_hash,
    default_branch_for_event,
    default_branch_for_state,
    has_pending_import,
    is_desired_state_current,
    is_duplicate_event,
)
from worker.normalize import AdoScope, NormalizedEvent, RepositoryRef


def _event() -> NormalizedEvent:
    from datetime import datetime, timezone

    return NormalizedEvent(
        source="ado",
        event_id="evt-1",
        event_type="repo.created",
        scope_id="scope",
        repository_id="repo",
        occurred_at=datetime(2026, 8, 9, tzinfo=timezone.utc),
        repository=RepositoryRef(name="demo"),
        ado=AdoScope(
            org_id="org",
            org_display_name="org",
            project_id="scope",
            project_name="proj",
        ),
        payload={"defaultBranch": "main"},
    )


def test_default_branch_for_event_returns_empty_when_unspecified() -> None:
    event = _event()
    assert default_branch_for_event(event) == "main"

    event_without_branch = NormalizedEvent(
        source=event.source,
        event_id=event.event_id,
        event_type=event.event_type,
        scope_id=event.scope_id,
        repository_id=event.repository_id,
        occurred_at=event.occurred_at,
        repository=event.repository,
        ado=event.ado,
        payload={},
    )
    assert default_branch_for_event(event_without_branch) == ""


def test_default_branch_for_state_preserves_existing_branch() -> None:
    event = _event()
    event_without_branch = NormalizedEvent(
        source=event.source,
        event_id=event.event_id,
        event_type="repo.renamed",
        scope_id=event.scope_id,
        repository_id=event.repository_id,
        occurred_at=event.occurred_at,
        repository=event.repository,
        ado=event.ado,
        payload={"previousRepoName": "old-name"},
    )
    existing = RepositoryState(
        repo_name="demo",
        snyk_target_id="target",
        default_branch="master",
        status="active",
        desired_state_hash="hash",
        last_event_id="evt-old",
        tag_applied=False,
        import_job_id="job",
        import_status="complete",
    )

    assert default_branch_for_state(event_without_branch, existing) == "master"
    assert default_branch_for_state(event_without_branch, None) == ""


def test_duplicate_event_detection() -> None:
    state = RepositoryState(
        repo_name="demo",
        snyk_target_id="target",
        default_branch="main",
        status="active",
        desired_state_hash="hash",
        last_event_id="evt-1",
        tag_applied=False,
        import_job_id="job",
        import_status="complete",
    )

    assert is_duplicate_event(state, "evt-1") is True
    assert is_duplicate_event(state, "evt-2") is False


def test_desired_state_current_requires_complete_import() -> None:
    desired = compute_desired_state_hash(
        event_type="repo.created",
        repo_name="demo",
        default_branch="main",
        status="active",
    )
    state = RepositoryState(
        repo_name="demo",
        snyk_target_id="target",
        default_branch="main",
        status="active",
        desired_state_hash=desired,
        last_event_id="evt-old",
        tag_applied=False,
        import_job_id="job",
        import_status="complete",
    )

    assert is_desired_state_current(state, desired) is True


def test_pending_import_guard() -> None:
    state = RepositoryState(
        repo_name="demo",
        snyk_target_id="",
        default_branch="main",
        status="pending",
        desired_state_hash="",
        last_event_id="evt-old",
        tag_applied=False,
        import_job_id="job",
        import_status="pending",
    )

    assert has_pending_import(state) is True
    assert has_pending_import(None) is False
