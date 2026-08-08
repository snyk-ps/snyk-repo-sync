"""Tests for sync-state table client."""

from unittest.mock import MagicMock

import pytest

from config.settings import SyncStateSettings
from sync_state.client import SyncStateStore


@pytest.fixture
def settings() -> SyncStateSettings:
    return SyncStateSettings(
        storage_account_endpoint="https://example.table.core.windows.net",
        table_name="SnykSyncState",
    )


def test_ensure_table_calls_create_if_not_exists(settings: SyncStateSettings) -> None:
    table_client = MagicMock()
    service_client = MagicMock()
    service_client.create_table_if_not_exists.return_value = table_client

    def factory(*, endpoint: str, credential: object) -> MagicMock:
        assert endpoint == settings.storage_account_endpoint
        return service_client

    store = SyncStateStore(settings, credential=object(), table_service_factory=factory)
    store.ensure_table()

    service_client.create_table_if_not_exists.assert_called_once_with("SnykSyncState")
    assert store._table_client is table_client
