"""Tests for ignore-policy persistence in sync state."""

import json
from unittest.mock import MagicMock

import pytest

from config.ignored_repos import ignore_policy_from_dict, parse_ignore_policy_document
from config.settings import SyncStateSettings
from sync_state.client import SyncStateStore


@pytest.fixture
def settings() -> SyncStateSettings:
    return SyncStateSettings(
        storage_account_endpoint="https://example.table.core.windows.net",
        table_name="SnykSyncState",
    )


def test_persist_and_load_ignore_policy(settings: SyncStateSettings) -> None:
    table_client = MagicMock()
    stored: dict[str, object] = {}

    def upsert_entity(*, entity: dict[str, object], mode: str) -> None:
        stored.update(entity)

    def get_entity(*, partition_key: str, row_key: str) -> dict[str, object]:
        return dict(stored)

    table_client.upsert_entity = upsert_entity
    table_client.get_entity = get_entity

    service_client = MagicMock()
    service_client.get_table_client.return_value = table_client

    store = SyncStateStore(
        settings,
        credential=object(),
        table_service_factory=lambda **_: service_client,
    )
    store._table_client = table_client

    policy = parse_ignore_policy_document(
        {
            "repos": [{"source": "azure-repos", "owner": "proj", "name": "archived"}],
            "patterns": [{"id": "Disabled", "filterType": "prefix", "patterns": ["disabled-"]}],
        },
    )
    store.persist_ignore_policy(policy)
    loaded = store.load_persisted_ignore_policy()

    assert loaded is not None
    assert loaded.explicit_entries[0].name == "archived"
    assert loaded.pattern_groups[0].id == "Disabled"


def test_load_persisted_ignore_policy_missing(settings: SyncStateSettings) -> None:
    table_client = MagicMock()
    table_client.get_entity.side_effect = Exception("not found")
    service_client = MagicMock()
    service_client.get_table_client.return_value = table_client

    store = SyncStateStore(
        settings,
        credential=object(),
        table_service_factory=lambda **_: service_client,
    )
    store._table_client = table_client

    from azure.core.exceptions import ResourceNotFoundError

    table_client.get_entity.side_effect = ResourceNotFoundError("missing")
    assert store.load_persisted_ignore_policy() is None


def test_ignore_policy_round_trip_dict() -> None:
    original = parse_ignore_policy_document(
        {
            "repos": [{"source": "github", "owner": "org", "name": "legacy"}],
            "patterns": [{"id": "Docs", "filterType": "suffix", "patterns": ["-docs"]}],
        },
    )
    restored = ignore_policy_from_dict(
        json.loads(json.dumps({"repos": [{"source": "github", "owner": "org", "name": "legacy"}], "patterns": [{"id": "Docs", "filterType": "suffix", "patterns": ["-docs"]}]})),
    )
    assert restored.explicit_entries[0].owner == original.explicit_entries[0].owner
