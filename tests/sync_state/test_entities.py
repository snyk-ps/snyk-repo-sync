"""Tests for sync-state entity models."""

from sync_state.entities import RepositoryState


def test_repository_state_round_trip() -> None:
    state = RepositoryState(
        repo_name="demo",
        snyk_target_id="target-1",
        default_branch="main",
        status="synced",
        desired_state_hash="abc",
        last_event_id="evt-1",
        tag_applied=True,
    )
    restored = RepositoryState.from_entity(state.to_entity("ado:project-1", "repo-1"))
    assert restored == state
