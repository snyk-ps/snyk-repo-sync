"""Azure Table Storage client for sync-state access."""

from typing import Any, Protocol

from azure.data.tables import TableClient, TableServiceClient
from azure.identity import DefaultAzureCredential

from config.settings import SyncStateSettings


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
