"""Tests for import branch resolution."""

from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest

from config.errors import ConfigError
from worker.import_branch import resolve_import_branch
from worker.normalize import AdoScope, NormalizedEvent, RepositoryRef


def _event(*, payload: dict[str, str] | None = None) -> NormalizedEvent:
    return NormalizedEvent(
        source="ado",
        event_id="evt-1",
        event_type="repo.created",
        scope_id="scope",
        repository_id="repo-id",
        occurred_at=datetime(2026, 8, 9, tzinfo=UTC),
        repository=RepositoryRef(name="demo"),
        ado=AdoScope(
            org_id="org",
            org_display_name="org",
            project_id="scope",
            project_name="proj",
        ),
        payload=payload or {},
    )


def test_resolve_import_branch_uses_event_payload() -> None:
    branch = resolve_import_branch(
        _event(payload={"defaultBranch": "main"}),
        None,
        ado=None,
    )

    assert branch == "main"


def test_resolve_import_branch_fetches_from_ado_when_unspecified() -> None:
    ado = MagicMock()
    ado.get_repository_default_branch.return_value = "master"

    branch = resolve_import_branch(_event(), None, ado=ado)

    assert branch == "master"
    ado.get_repository_default_branch.assert_called_once_with("repo-id")


def test_resolve_import_branch_requires_ado_client_for_enrichment() -> None:
    with pytest.raises(
        ConfigError,
        match="ADO default-branch enrichment requires ado.organization and ADO_PAT",
    ):
        resolve_import_branch(_event(), None, ado=None)
