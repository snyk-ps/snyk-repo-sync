"""Azure Table Storage sync-state access."""

from sync_state.client import SyncStateStore
from sync_state.entities import RepositoryState

__all__ = ["RepositoryState", "SyncStateStore"]
