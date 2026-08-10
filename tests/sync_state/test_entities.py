"""Tests for sync-state entity models."""

from sync_state.entities import RepositoryState


def test_repository_state_round_trip() -> None:
    state = RepositoryState(
        repo_name="demo",
        snyk_target_id="target-1",
        default_branch="main",
        status="active",
        desired_state_hash="abc",
        last_event_id="evt-1",
        tag_applied=True,
        import_job_id="job-1",
        import_status="complete",
    )
    restored = RepositoryState.from_entity(state.to_entity("ado:project-1", "repo-1"))
    assert restored == state


def test_repository_state_from_entity_defaults_import_fields() -> None:
    restored = RepositoryState.from_entity(
        {
            "repoName": "demo",
            "snykTargetId": "",
            "defaultBranch": "main",
            "status": "pending",
            "desiredStateHash": "",
            "lastEventId": "",
            "tagApplied": False,
        },
    )
    assert restored.import_job_id == ""
    assert restored.import_status == "pending"
