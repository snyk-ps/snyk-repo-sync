"""Service Bus queue consumer for the worker."""

import logging
from typing import Any, Protocol

from azure.identity import DefaultAzureCredential
from azure.servicebus import ServiceBusClient, ServiceBusReceivedMessage

from config.settings import WorkerSettings
from sync_state import SyncStateStore
from worker.handler import handle_queue_message
from worker.message import INVALID_MESSAGE_REASON, MessageParseError
from worker.normalize import INVALID_NORMALIZATION_REASON, NormalizationError

logger = logging.getLogger(__name__)

DEFAULT_MAX_WAIT_TIME = 5


class QueueReceiver(Protocol):
    """Minimal receiver interface for queue message handling."""

    def receive_messages(self, *, max_message_count: int, max_wait_time: int): ...

    def complete_message(self, message: ServiceBusReceivedMessage) -> None: ...

    def dead_letter_message(
        self,
        message: ServiceBusReceivedMessage,
        *,
        reason: str | None = None,
        error_description: str | None = None,
    ) -> None: ...


class ServiceBusClientFactory(Protocol):
    """Factory protocol for ServiceBusClient construction."""

    def __call__(
        self,
        *,
        fully_qualified_namespace: str,
        credential: Any,
    ) -> ServiceBusClient: ...


def _default_service_bus_client_factory(
    *,
    fully_qualified_namespace: str,
    credential: Any,
) -> ServiceBusClient:
    return ServiceBusClient(
        fully_qualified_namespace=fully_qualified_namespace,
        credential=credential,
    )


def _message_body(message: ServiceBusReceivedMessage) -> bytes:
    body = message.body
    if isinstance(body, bytes):
        return body
    if isinstance(body, bytearray):
        return bytes(body)
    if isinstance(body, memoryview):
        return body.tobytes()
    if isinstance(body, str):
        return body.encode("utf-8")
    if isinstance(body, (list, tuple)):
        return b"".join(
            part if isinstance(part, bytes) else part.encode("utf-8") for part in body
        )
    return b"".join(body)


def process_message(message: ServiceBusReceivedMessage, receiver: QueueReceiver) -> None:
    """Process one queue message: parse, complete, or dead-letter.

    Args:
        message: Received Service Bus message.
        receiver: Active queue receiver used for settlement.
    """
    body = _message_body(message)
    try:
        handle_queue_message(body)
    except MessageParseError as exc:
        logger.warning("Dead-lettering message with invalid queue message: %s", exc)
        receiver.dead_letter_message(
            message,
            reason=INVALID_MESSAGE_REASON,
            error_description=str(exc),
        )
        return
    except NormalizationError as exc:
        logger.warning("Dead-lettering message with invalid normalization: %s", exc)
        receiver.dead_letter_message(
            message,
            reason=INVALID_NORMALIZATION_REASON,
            error_description=str(exc),
        )
        return

    receiver.complete_message(message)
    logger.info("Completed queue message message_id=%s", message.message_id)


class WorkerConsumer:
    """Long-running worker that consumes queue messages from Service Bus."""

    def __init__(
        self,
        settings: WorkerSettings,
        sync_state: SyncStateStore,
        *,
        max_wait_time: int = DEFAULT_MAX_WAIT_TIME,
        credential: Any | None = None,
        client_factory: ServiceBusClientFactory | None = None,
    ) -> None:
        self._settings = settings
        self._sync_state = sync_state
        self._max_wait_time = max_wait_time
        self._credential = credential if credential is not None else DefaultAzureCredential()
        self._client_factory = client_factory or _default_service_bus_client_factory

    def run(self) -> None:
        """Receive and process messages until interrupted."""
        logger.info(
            "Starting worker consumer queue_name=%s namespace=%s table_name=%s",
            self._settings.service_bus.queue_name,
            self._settings.service_bus.fully_qualified_namespace,
            self._sync_state.table_name,
        )
        with self._client_factory(
            fully_qualified_namespace=self._settings.service_bus.fully_qualified_namespace,
            credential=self._credential,
        ) as client:
            with client.get_queue_receiver(
                self._settings.service_bus.queue_name,
                max_wait_time=self._max_wait_time,
            ) as receiver:
                for message in receiver:
                    process_message(message, receiver)
