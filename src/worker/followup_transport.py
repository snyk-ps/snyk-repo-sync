"""Queue transport interface for follow-up scheduling and settlement."""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol

from azure.servicebus import ServiceBusMessage, ServiceBusReceivedMessage

logger = logging.getLogger(__name__)


class FollowUpTransport(Protocol):
    """Receive, settle, and delay worker messages on one queue."""

    def receive(self, *, max_wait_seconds: int) -> list[Any]:
        """Return the next available messages, waiting up to ``max_wait_seconds``."""

    def complete(self, message: Any) -> None:
        """Remove a successfully processed message."""

    def dead_letter(
        self,
        message: Any,
        *,
        reason: str,
        description: str | None = None,
    ) -> None:
        """Settle a message as unrecoverable and retain its body for operators."""

    def schedule(self, body: dict[str, Any], *, delay_seconds: int) -> None:
        """Enqueue a follow-up body that becomes visible after ``delay_seconds``."""


def message_id_of(message: Any) -> str:
    """Return a loggable id for a Service Bus or storage-queue message."""
    message_id = getattr(message, "message_id", None)
    if isinstance(message_id, str) and message_id:
        return message_id
    storage_id = getattr(message, "id", None)
    if storage_id is not None:
        return str(storage_id)
    return "unknown"


class ServiceBusFollowUpTransport:
    """Service Bus queue adapter for the follow-up transport interface."""

    def __init__(self, receiver: Any, sender: Any | None = None) -> None:
        self._receiver = receiver
        self._sender = sender

    def receive(self, *, max_wait_seconds: int) -> list[Any]:
        """Receive up to one message from the Service Bus queue."""
        messages = self._receiver.receive_messages(
            max_message_count=1,
            max_wait_time=max_wait_seconds,
        )
        return list(messages)

    def complete(self, message: ServiceBusReceivedMessage) -> None:
        """Complete a Service Bus message."""
        self._receiver.complete_message(message)

    def dead_letter(
        self,
        message: ServiceBusReceivedMessage,
        *,
        reason: str,
        description: str | None = None,
    ) -> None:
        """Dead-letter a Service Bus message."""
        self._receiver.dead_letter_message(
            message,
            reason=reason,
            error_description=description,
        )

    def schedule(self, body: dict[str, Any], *, delay_seconds: int) -> None:
        """Schedule a follow-up on the Service Bus queue."""
        if self._sender is None:
            logger.error("Follow-up messages requested but queue scheduler is unavailable")
            return
        schedule_at = datetime.now(tz=UTC) + timedelta(seconds=delay_seconds)
        self._sender.schedule_messages(
            [ServiceBusMessage(json.dumps(body))],
            schedule_time_utc=schedule_at,
        )
        logger.info(
            "Scheduled follow-up syncPhase=%s delay_seconds=%s",
            body.get("syncPhase"),
            delay_seconds,
        )
