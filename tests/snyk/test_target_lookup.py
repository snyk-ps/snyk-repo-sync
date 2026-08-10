"""Tests for Snyk target record matching helpers."""

from snyk.target_lookup import (
    normalize_repo_name,
    parse_project_ids,
    parse_target_records,
    select_target_id,
)


def test_normalize_repo_name_strips_git_suffix() -> None:
    assert normalize_repo_name("demo.git") == "demo"
    assert normalize_repo_name("demo") == "demo"


def test_select_target_id_prefers_owner_and_branch() -> None:
    records = parse_target_records(
        {
            "data": [
                {"id": "target-a", "attributes": {"display_name": "demo"}},
                {"id": "target-b", "attributes": {"display_name": "proj/demo(main)"}},
            ],
        },
    )

    target_id = select_target_id(
        records,
        owner="proj",
        repo_name="demo",
        branch="main",
    )

    assert target_id == "target-b"


def test_parse_project_ids() -> None:
    assert parse_project_ids({"data": [{"id": "p1"}, {"id": "p2"}]}) == ["p1", "p2"]
