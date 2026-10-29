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


def test_repository_state_round_trips_resolved_org() -> None:
    state = RepositoryState(
        repo_name="demo",
        snyk_target_id="target-1",
        default_branch="main",
        status="active",
        desired_state_hash="abc",
        last_event_id="evt-1",
        tag_applied=False,
        import_job_id="job-1",
        import_status="complete",
        snyk_org_id="org-1",
        snyk_integration_type="github-enterprise",
    )

    restored = RepositoryState.from_entity(state.to_entity("github:contoso", "repo-1"))

    assert restored.snyk_org_id == "org-1"
    assert restored.snyk_integration_type == "github-enterprise"
    assert restored == state


def test_repository_state_without_org_properties_has_no_stored_org() -> None:
    restored = RepositoryState.from_entity(
        {
            "repoName": "demo",
            "snykTargetId": "",
            "defaultBranch": "main",
            "status": "pending",
            "desiredStateHash": "",
            "lastEventId": "",
            "tagApplied": False,
            "snykOrgId": "  ",
            "snykIntegrationType": "github",
        },
    )

    assert restored.snyk_org_id is None
    assert restored.snyk_integration_type is None


def test_repository_state_upsert_replaces_stored_org_id() -> None:
    previous = RepositoryState(
        repo_name="demo",
        snyk_target_id="",
        default_branch="main",
        status="pending",
        desired_state_hash="hash",
        last_event_id="evt-1",
        tag_applied=False,
        import_job_id="job-1",
        import_status="pending",
        snyk_org_id="org-old",
        snyk_integration_type="github",
    )
    replacement = RepositoryState(
        repo_name="demo",
        snyk_target_id="",
        default_branch="main",
        status="pending",
        desired_state_hash="hash",
        last_event_id="evt-2",
        tag_applied=False,
        import_job_id="job-2",
        import_status="pending",
        snyk_org_id="org-new",
        snyk_integration_type="github-enterprise",
    )

    entity = replacement.to_entity("github:contoso", "repo-1")

    assert previous.to_entity("github:contoso", "repo-1")["snykOrgId"] == "org-old"
    assert entity["snykOrgId"] == "org-new"
    assert entity["snykIntegrationType"] == "github-enterprise"
    assert "org-old" not in entity.values()


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
