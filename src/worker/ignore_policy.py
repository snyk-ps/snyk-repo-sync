"""Runtime ignore-policy loading and refresh."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from config.errors import ConfigError
from config.ignored_repos import IgnorePolicy, load_ignore_policy
from sync_state.client import SyncStateStore

logger = logging.getLogger(__name__)


@dataclass
class IgnorePolicyState:
    """Mutable holder for the active ignore policy."""

    policy: IgnorePolicy | None = None

    def load_from_file(self, path: Path, sync_state: SyncStateStore) -> IgnorePolicy:
        """Load ignore policy from disk and persist to sync state."""
        policy = load_ignore_policy(path)
        sync_state.persist_ignore_policy(policy)
        self.policy = policy
        return policy

    def reload(self, path: Path, sync_state: SyncStateStore) -> IgnorePolicy | None:
        """Reload policy from disk, falling back to persisted policy on failure."""
        try:
            return self.load_from_file(path, sync_state)
        except ConfigError as exc:
            logger.error(
                "Ignore policy reload failed path=%s error=%s outcome=using_persisted_policy",
                path,
                exc,
            )
            persisted = sync_state.load_persisted_ignore_policy()
            if persisted is not None:
                self.policy = persisted
                logger.info("Using persisted ignore policy after reload failure path=%s", path)
                return persisted
            if self.policy is not None:
                logger.info("Using in-memory ignore policy after reload failure path=%s", path)
                return self.policy
            logger.error("No ignore policy available after reload failure path=%s", path)
            return None
