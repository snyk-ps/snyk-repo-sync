"""Tests for sync-state repository access."""

from unittest.mock import MagicMock

import pytest

from config.settings import SyncStateSettings
from sync_state.client import SyncStateStore
from sync_state.entities import RepositoryState


@pytest.fixture
def settings() -> SyncStateSettings:
    return SyncStateSettings(
        storage_account_endpoint="https://example.table.core.windows.net",
        table_name="SnykSyncState",
    )


def test_get_repository_returns_none_when_missing(settings: SyncStateSettings) -> None:
    table_client = MagicMock()
    table_client.get_entity.side_effect = __import__(
        "azure.core.exceptions",
        fromlist=["ResourceNotFoundError"],
    ).ResourceNotFoundError("missing")
    service_client = MagicMock()
    service_client.get_table_client.return_value = table_client

    store = SyncStateStore(
        settings,
        credential=object(),
        table_service_factory=lambda **_: service_client,
    )
    store._table_client = table_client

    assert store.get_repository(source="ado", scope_id="scope", repository_id="repo") is None


def test_upsert_repository_writes_entity(settings: SyncStateSettings) -> None:
    table_client = MagicMock()
    store = SyncStateStore(
        settings,
        credential=object(),
        table_service_factory=lambda **_: MagicMock(),
    )
    store._table_client = table_client
    state = RepositoryState(
        repo_name="demo",
        snyk_target_id="",
        default_branch="main",
        status="pending",
        desired_state_hash="hash",
        last_event_id="evt",
        tag_applied=False,
        import_job_id="job",
        import_status="pending",
    )

    store.upsert_repository(state, source="ado", scope_id="scope", repository_id="repo")

    table_client.upsert_entity.assert_called_once()
    entity = table_client.upsert_entity.call_args.kwargs["entity"]
    assert entity["importStatus"] == "pending"
    assert entity["PartitionKey"] == "ado:scope"


def test_count_pending_imports(settings: SyncStateSettings) -> None:
    table_client = MagicMock()
    table_client.query_entities.return_value = [{"PartitionKey": "ado:1"}, {"PartitionKey": "ado:2"}]
    store = SyncStateStore(
        settings,
        credential=object(),
        table_service_factory=lambda **_: MagicMock(),
    )
    store._table_client = table_client

    assert store.count_pending_imports() == 2
