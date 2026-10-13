"""GitHub event intake from the Kafka event connector.

The HTTP client is intentionally absent. The REST contract is not available yet.
"""

from typing import Any, Protocol

from config.errors import ConfigError
from config.settings import EVENT_CONNECTOR_PENDING_MESSAGE


class GitHubEventSource(Protocol):
    """Consumption-only source of GitHub lifecycle event bodies."""

    def receive(self, *, max_wait_seconds: int) -> list[Any]:
        """Return the next GitHub event messages."""

    def complete(self, message: Any) -> None:
        """Acknowledge a successfully processed event."""

    def dead_letter(
        self,
        message: Any,
        *,
        reason: str,
        description: str | None = None,
    ) -> None:
        """Reject an event that cannot be processed."""


def open_github_event_source() -> GitHubEventSource:
    """Open the event connector.

    Raises:
        ConfigError: Always. No HTTP client is implemented.
    """
    raise ConfigError(EVENT_CONNECTOR_PENDING_MESSAGE)
