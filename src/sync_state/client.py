"""Azure Table Storage client for sync-state access."""

import json
from dataclasses import dataclass
from typing import Any, Protocol

from azure.core.exceptions import ResourceNotFoundError
from azure.data.tables import TableClient, TableServiceClient
from azure.identity import DefaultAzureCredential

from config.ignored_repos import (
    IGNORE_POLICY_META_PARTITION,
    IGNORE_POLICY_META_ROW_KEY,
    IgnorePolicy,
    ignore_policy_from_dict,
    ignore_policy_to_dict,
)
from config.settings import SyncStateSettings
from sync_state.entities import RepositoryState, repository_partition_key


class TableServiceClientFactory(Protocol):
    """Factory protocol for TableServiceClient construction."""

    def __call__(
        self,
        *,
        endpoint: str,
        credential: Any,
    ) -> TableServiceClient: ...


def _default_table_service_client_factory(
    *,
    endpoint: str,
    credential: Any,
) -> TableServiceClient:
    return TableServiceClient(endpoint=endpoint, credential=credential)


@dataclass(frozen=True)
class ActiveRepositoryRow:
    """Active synced repository row for ignore reconciliation."""

    source: str
    scope_id: str
    repository_id: str
    state: RepositoryState


class SyncStateStore:
    """Access sync-state repository entities in Azure Table Storage."""

    def __init__(
        self,
        settings: SyncStateSettings,
        *,
        credential: Any | None = None,
        table_service_factory: TableServiceClientFactory | None = None,
    ) -> None:
        self._settings = settings
        self._credential = credential if credential is not None else DefaultAzureCredential()
        self._table_service_factory = (
            table_service_factory or _default_table_service_client_factory
        )
        self._table_client: TableClient | None = None

    @property
    def table_name(self) -> str:
        """Return the configured table name."""
        return self._settings.table_name

    def _table(self) -> TableClient:
        if self._table_client is None:
            service = self._table_service_factory(
                endpoint=self._settings.storage_account_endpoint,
                credential=self._credential,
            )
            self._table_client = service.get_table_client(self._settings.table_name)
        return self._table_client

    def ensure_table(self) -> None:
        """Create the sync-state table when it does not already exist."""
        service = self._table_service_factory(
            endpoint=self._settings.storage_account_endpoint,
            credential=self._credential,
        )
        self._table_client = service.create_table_if_not_exists(self._settings.table_name)

    def get_repository(
        self,
        *,
        source: str,
        scope_id: str,
        repository_id: str,
    ) -> RepositoryState | None:
        """Return repository state for a provider repository id."""
        partition_key = repository_partition_key(source, scope_id)
        try:
            entity = self._table().get_entity(partition_key=partition_key, row_key=repository_id)
        except ResourceNotFoundError:
            return None
        return RepositoryState.from_entity(entity)

    def upsert_repository(
        self,
        state: RepositoryState,
        *,
        source: str,
        scope_id: str,
        repository_id: str,
    ) -> None:
        """Create or replace repository state for a provider repository id."""
        partition_key = repository_partition_key(source, scope_id)
        entity = state.to_entity(partition_key, repository_id)
        self._table().upsert_entity(entity=entity, mode="merge")

    def count_pending_imports(self) -> int:
        """Count repository rows with ``importStatus=pending``."""
        filter_query = "importStatus eq 'pending'"
        count = 0
        for _ in self._table().query_entities(query_filter=filter_query, select=["PartitionKey"]):
            count += 1
        return count

    def persist_ignore_policy(self, policy: IgnorePolicy) -> None:
        """Persist loaded ignore policy to the sync-state meta row."""
        entity = {
            "PartitionKey": IGNORE_POLICY_META_PARTITION,
            "RowKey": IGNORE_POLICY_META_ROW_KEY,
            "policyJson": json.dumps(ignore_policy_to_dict(policy)),
        }
        self._table().upsert_entity(entity=entity, mode="replace")

    def load_persisted_ignore_policy(self) -> IgnorePolicy | None:
        """Return the last persisted ignore policy, if any."""
        try:
            entity = self._table().get_entity(
                partition_key=IGNORE_POLICY_META_PARTITION,
                row_key=IGNORE_POLICY_META_ROW_KEY,
            )
        except ResourceNotFoundError:
            return None
        raw_json = entity.get("policyJson")
        if not isinstance(raw_json, str) or not raw_json.strip():
            return None
        try:
            document = json.loads(raw_json)
        except json.JSONDecodeError:
            return None
        return ignore_policy_from_dict(document)

    def list_active_repositories(self) -> list[ActiveRepositoryRow]:
        """Return repository rows with completed imports and active status."""
        filter_query = "importStatus eq 'complete' and status eq 'active'"
        rows: list[ActiveRepositoryRow] = []
        for entity in self._table().query_entities(query_filter=filter_query):
            partition_key = str(entity.get("PartitionKey", ""))
            repository_id = str(entity.get("RowKey", ""))
            if partition_key.startswith("_") or ":" not in partition_key:
                continue
            source, scope_id = partition_key.split(":", 1)
            rows.append(
                ActiveRepositoryRow(
                    source=source,
                    scope_id=scope_id,
                    repository_id=repository_id,
                    state=RepositoryState.from_entity(entity),
                ),
            )
        return rows
