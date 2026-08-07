"""Service Bus queue consumer for the worker."""

import logging
from typing import Protocol

from azure.servicebus import ServiceBusClient, ServiceBusReceivedMessage

from config.service_bus import ServiceBusSettings
from worker.envelope import EnvelopeValidationError
from worker.handler import handle_transport_message
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


def _message_body(message: ServiceBusReceivedMessage) -> bytes:
    body = message.body
    if isinstance(body, bytes):
        return body
    if isinstance(body, (list, tuple)):
        return b"".join(part if isinstance(part, bytes) else part.encode("utf-8") for part in body)
    return str(body).encode("utf-8")


def process_message(message: ServiceBusReceivedMessage, receiver: QueueReceiver) -> None:
    """Process one queue message: validate envelope, complete or dead-letter.

    Args:
        message: Received Service Bus message.
        receiver: Active queue receiver used for settlement.
    """
    body = _message_body(message)
    try:
        handle_transport_message(body)
    except EnvelopeValidationError as exc:
        logger.warning(
            "Dead-lettering message with invalid transport envelope",
            extra={"reason": str(exc)},
        )
        receiver.dead_letter_message(
            message,
            reason="InvalidEnvelope",
            error_description=str(exc),
        )
        return
    except NormalizationError as exc:
        logger.warning(
            "Dead-lettering message with invalid normalization",
            extra={"reason": str(exc)},
        )
        receiver.dead_letter_message(
            message,
            reason=INVALID_NORMALIZATION_REASON,
            error_description=str(exc),
        )
        return

    receiver.complete_message(message)
    logger.info("Completed transport message", extra={"message_id": message.message_id})


class WorkerConsumer:
    """Long-running worker that consumes transport messages from Service Bus."""

    def __init__(
        self,
        settings: ServiceBusSettings,
        *,
        max_wait_time: int = DEFAULT_MAX_WAIT_TIME,
        client_factory=ServiceBusClient,
    ) -> None:
        self._settings = settings
        self._max_wait_time = max_wait_time
        self._client_factory = client_factory

    def run(self) -> None:
        """Receive and process messages until interrupted."""
        logger.info(
            "Starting worker consumer",
            extra={"queue_name": self._settings.queue_name},
        )
        with self._client_factory.from_connection_string(
            self._settings.connection_string
        ) as client:
            with client.get_queue_receiver(
                self._settings.queue_name,
                max_wait_time=self._max_wait_time,
            ) as receiver:
                for message in receiver:
                    process_message(message, receiver)
