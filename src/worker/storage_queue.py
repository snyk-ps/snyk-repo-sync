"""Azure Storage queue transport for worker follow-up messages."""

from __future__ import annotations

import json
import logging
import time
from collections.abc import Callable
from threading import Event
from typing import Any

from azure.identity import DefaultAzureCredential
from azure.storage.queue import QueueServiceClient

from config.settings import MAX_VISIBILITY_TIMEOUT_SECONDS, StorageQueueSettings, WorkerSettings
from worker.followup_transport import message_id_of
from worker.handler import process_message_body
from worker.lifecycle import WorkerSyncDependencies
from worker.message import INVALID_MESSAGE_REASON

logger = logging.getLogger(__name__)

MAX_DEQUEUE_COUNT = 10
MAX_DEQUEUE_COUNT_REASON = "MaxDequeueCountExceeded"
_FOLLOW_UP_PHASES = frozenset({"import_poll", "lifecycle_deferred", "ignore_migration"})


class StorageQueueTransport:
    """Follow-up queue backed by an Azure Storage queue and a poison queue."""

    def __init__(
        self,
        settings: StorageQueueSettings,
        *,
        queue_client: Any,
        poison_client: Any,
    ) -> None:
        self._settings = settings
        self._queue = queue_client
        self._poison = poison_client

    def receive(self) -> list[Any]:
        """Return at most one visible message, locking it for the visibility timeout."""
        messages = self._queue.receive_messages(
            messages_per_page=1,
            visibility_timeout=self._settings.visibility_timeout_seconds,
            max_messages=1,
        )
        return list(messages)

    def complete(self, message: Any) -> None:
        """Delete a successfully processed message."""
        self._delete(message)
        logger.info("Completed queue message message_id=%s", message_id_of(message))

    def dead_letter(
        self,
        message: Any,
        *,
        reason: str,
        description: str | None = None,
    ) -> None:
        """Copy the original body to the poison queue, then delete the source message.

        ``description`` is accepted for transport parity and is not written into the body.
        """
        del description
        message_id = message_id_of(message)
        self._poison.send_message(_message_text(message))
        logger.error(
            "Dead-lettered queue message message_id=%s reason=%s",
            message_id,
            reason,
        )
        try:
            self._delete(message)
        except Exception:
            logger.error(
                "Failed to delete source message after poison copy message_id=%s reason=%s",
                message_id,
                reason,
            )
            raise

    def schedule(self, body: dict[str, Any], *, delay_seconds: int) -> None:
        """Enqueue a follow-up that stays hidden until ``delay_seconds`` elapses."""
        if delay_seconds < 0 or delay_seconds > MAX_VISIBILITY_TIMEOUT_SECONDS:
            raise ValueError(
                "follow-up delay must be between 0 and "
                f"{MAX_VISIBILITY_TIMEOUT_SECONDS} seconds, got {delay_seconds}"
            )
        self._queue.send_message(json.dumps(body), visibility_timeout=delay_seconds)
        logger.info(
            "Scheduled follow-up syncPhase=%s delay_seconds=%s",
            body.get("syncPhase"),
            delay_seconds,
        )

    def process(
        self,
        message: Any,
        *,
        settings: WorkerSettings,
        sync_deps: WorkerSyncDependencies | None = None,
    ) -> None:
        """Settle one storage-queue message. Non-follow-up bodies are poison-settled."""
        if _dequeue_count(message) >= MAX_DEQUEUE_COUNT:
            self.dead_letter(message, reason=MAX_DEQUEUE_COUNT_REASON)
            return

        text = _message_text(message)
        if not _is_follow_up(text):
            self.dead_letter(
                message,
                reason=INVALID_MESSAGE_REASON,
                description="storage queue messages must be internal follow-ups",
            )
            return

        outcome = process_message_body(
            text,
            scope_mapping=settings.scope_mapping,
            sync_deps=sync_deps,
        )
        if outcome.status == "failed":
            self.dead_letter(
                message,
                reason=outcome.reason or "Unknown",
                description=outcome.description,
            )
            return

        assert outcome.result is not None
        result = outcome.result
        for followup in result.scheduled_followups:
            self.schedule(followup.body, delay_seconds=followup.delay_seconds)
        self.complete(message)

    def run(
        self,
        *,
        settings: WorkerSettings,
        sync_deps: WorkerSyncDependencies | None = None,
        sleep: Callable[[float], None] = time.sleep,
        stop_event: Event | None = None,
    ) -> None:
        """Poll until interrupted. An empty queue waits and does not stop the loop."""
        wait_seconds = self._settings.receive_max_wait_seconds
        while stop_event is None or not stop_event.is_set():
            messages = self.receive()
            if not messages:
                if stop_event is None:
                    sleep(wait_seconds)
                else:
                    stop_event.wait(wait_seconds)
                continue
            for message in messages:
                if stop_event is not None and stop_event.is_set():
                    return
                self.process(message, settings=settings, sync_deps=sync_deps)

    def _delete(self, message: Any) -> None:
        self._queue.delete_message(message.id, message.pop_receipt)


def open_storage_queue_transport(
    settings: StorageQueueSettings,
    *,
    credential: Any | None = None,
) -> StorageQueueTransport:
    """Open the follow-up queue and its poison queue with ``DefaultAzureCredential``.

    The worker does not create either queue. Callers on the kafka path still exit
    before polling until the event-connector REST client exists.
    """
    resolved = credential if credential is not None else DefaultAzureCredential()
    service = QueueServiceClient(account_url=settings.queue_service_url, credential=resolved)
    return StorageQueueTransport(
        settings,
        queue_client=service.get_queue_client(settings.queue_name),
        poison_client=service.get_queue_client(settings.poison_queue_name),
    )


def _dequeue_count(message: Any) -> int:
    count = getattr(message, "dequeue_count", 0)
    if isinstance(count, int) and not isinstance(count, bool):
        return count
    return 0


def _message_text(message: Any) -> str:
    content = getattr(message, "content", "")
    if isinstance(content, bytes):
        return content.decode("utf-8")
    if isinstance(content, str):
        return content
    return "" if content is None else str(content)


def _is_follow_up(text: str) -> bool:
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return False
    if not isinstance(data, dict):
        return False
    return data.get("syncPhase") in _FOLLOW_UP_PHASES
