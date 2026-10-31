"""Tests for v1 project ignore matching."""

import pytest

from snyk.client import SnykProject
from worker.project_match import ProjectMatchError, match_projects


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


def test_manifest_match_across_branches() -> None:
    matches = match_projects(
        [_project("src", target_reference="develop")],
        [_project("dst", target_reference="main")],
        import_branch="main",
        source_ids_with_ignores={"src"},
    )

    assert matches == {"src": "dst"}


def test_unmatched_project_with_ignores_fails() -> None:
    with pytest.raises(ProjectMatchError):
        match_projects(
            [_project("src", target_file="package.json")],
            [_project("dst", target_file="requirements.txt", project_type="pip")],
            import_branch="main",
            source_ids_with_ignores={"src"},
        )


def test_source_without_ignores_does_not_require_a_match() -> None:
    matches = match_projects(
        [_project("src", target_file="missing.txt")],
        [],
        import_branch="main",
        source_ids_with_ignores=set(),
    )

    assert matches == {}


def test_empty_target_file_matches_on_type_when_unique() -> None:
    matches = match_projects(
        [_project("src", target_file="", target_reference="develop")],
        [_project("dst", target_file="", target_reference="main")],
        import_branch="main",
        source_ids_with_ignores={"src"},
    )

    assert matches == {"src": "dst"}


def test_same_branch_tie_prefers_import_branch() -> None:
    matches = match_projects(
        [
            _project("old", target_reference="develop"),
            _project("current", target_reference="main"),
        ],
        [_project("dst", target_reference="main")],
        import_branch="main",
        source_ids_with_ignores={"old", "current"},
    )

    assert matches == {"current": "dst"}


def test_remaining_tie_with_ignores_fails() -> None:
    with pytest.raises(ProjectMatchError):
        match_projects(
            [
                _project("a", target_reference="develop"),
                _project("b", target_reference="release"),
            ],
            [_project("dst")],
            import_branch="main",
            source_ids_with_ignores={"a"},
        )


def test_deactivated_source_matches_active_destination() -> None:
    matches = match_projects(
        [_project("src", target_reference="develop", deactivated=True)],
        [_project("dst", target_reference="main")],
        import_branch="main",
        source_ids_with_ignores={"src"},
    )

    assert matches == {"src": "dst"}


def test_deactivated_destination_is_not_a_match() -> None:
    with pytest.raises(ProjectMatchError):
        match_projects(
            [_project("src", target_reference="develop", deactivated=True)],
            [_project("dst", target_reference="main", deactivated=True)],
            import_branch="main",
            source_ids_with_ignores={"src"},
        )
