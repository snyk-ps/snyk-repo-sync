"""Tests for Snyk target id resolution."""

from datetime import datetime, timezone
from unittest.mock import MagicMock

from sync_state.entities import RepositoryState
from worker.normalize import AdoScope, NormalizedEvent, RepositoryRef
from worker.target_resolve import ensure_snyk_target_id, target_lookup_for_event


def _event(event_type: str, *, payload: dict[str, str] | None = None) -> NormalizedEvent:
    return NormalizedEvent(
        source="ado",
        event_id="evt-1",
        event_type=event_type,  # type: ignore[arg-type]
        scope_id="scope",
        repository_id="repo",
        occurred_at=datetime(2026, 8, 9, tzinfo=timezone.utc),
        repository=RepositoryRef(name="new-name"),
        ado=AdoScope(
            org_id="org",
            org_display_name="org",
            project_id="scope",
            project_name="proj",
        ),
        payload=payload or {},
    )


def test_ensure_snyk_target_id_uses_state_when_present() -> None:
    snyk = MagicMock()

    target_id = ensure_snyk_target_id(
        "org-1",
        stored_id="target-1",
        lookup=target_lookup_for_event(_event("repo.deleted"), None),
        snyk=snyk,
    )

    assert target_id == "target-1"
    snyk.find_target_id.assert_not_called()


def test_target_lookup_for_rename_uses_previous_repo_name() -> None:
    state = RepositoryState(
        repo_name="old-name",
        snyk_target_id="target-1",
        default_branch="main",
        status="active",
        desired_state_hash="hash",
        last_event_id="evt-old",
        tag_applied=False,
        import_job_id="job-1",
        import_status="complete",
    )
    lookup = target_lookup_for_event(
        _event("repo.renamed", payload={"previousRepoName": "old-name"}),
        state,
    )

    assert lookup.repo_name == "old-name"
    assert lookup.branch == "main"


def test_ensure_snyk_target_id_falls_back_to_rest_lookup() -> None:
    snyk = MagicMock()
    snyk.find_target_id.return_value = "target-rest"

    lookup = target_lookup_for_event(_event("repo.deleted"), None)
    target_id = ensure_snyk_target_id(
        "org-1",
        stored_id="",
        lookup=lookup,
        snyk=snyk,
    )

    assert target_id == "target-rest"
    snyk.find_target_id.assert_called_once_with(
        "org-1",
        owner="proj",
        repo_name="new-name",
        branch="",
    )
