"""Service Bus queue consumer for the worker."""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol

from azure.identity import DefaultAzureCredential
from azure.servicebus import ServiceBusClient, ServiceBusMessage, ServiceBusReceivedMessage

from config.settings import WorkerSettings
from snyk.client import SnykApiError
from sync_state import SyncStateStore
from worker.handler import HandleResult, handle_queue_message
from worker.lifecycle import WorkerSyncDependencies
from worker.message import INVALID_MESSAGE_REASON, MessageParseError
from worker.normalize import INVALID_NORMALIZATION_REASON, NormalizationError

logger = logging.getLogger(__name__)


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


class QueueScheduler(Protocol):
    """Minimal sender interface for scheduling follow-up messages."""

    def schedule_messages(
        self,
        messages: list[ServiceBusMessage],
        *,
        schedule_time_utc: datetime,
    ) -> list[int]: ...


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


def _settle_message(
    message: ServiceBusReceivedMessage,
    receiver: QueueReceiver,
    result: HandleResult,
) -> None:
    if result.settlement == "dead_letter":
        receiver.dead_letter_message(
            message,
            reason=result.dead_letter_reason,
            error_description=result.dead_letter_description,
        )
        logger.error(
            "Dead-lettered queue message message_id=%s reason=%s",
            message.message_id,
            result.dead_letter_reason,
        )
        return

    receiver.complete_message(message)
    logger.info("Completed queue message message_id=%s", message.message_id)


def _schedule_followups(
    followups: tuple[Any, ...],
    scheduler: QueueScheduler | None,
) -> None:
    if not followups:
        return
    if scheduler is None:
        logger.error("Follow-up messages requested but queue scheduler is unavailable")
        return
    for followup in followups:
        schedule_at = datetime.now(tz=UTC) + timedelta(seconds=followup.delay_seconds)
        scheduler.schedule_messages(
            [ServiceBusMessage(json.dumps(followup.body))],
            schedule_time_utc=schedule_at,
        )
        logger.info(
            "Scheduled follow-up syncPhase=%s delay_seconds=%s",
            followup.body.get("syncPhase"),
            followup.delay_seconds,
        )


def process_message(
    message: ServiceBusReceivedMessage,
    receiver: QueueReceiver,
    *,
    settings: WorkerSettings,
    sync_deps: WorkerSyncDependencies | None = None,
    scheduler: QueueScheduler | None = None,
) -> None:
    """Process one queue message: parse, complete, schedule follow-ups, or dead-letter."""
    body = _message_body(message)
    try:
        result = handle_queue_message(
            body,
            scope_mapping=settings.scope_mapping,
            sync_deps=sync_deps,
        )
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
    except SnykApiError as exc:
        logger.error("Dead-lettering message after Snyk API failure: %s", exc)
        receiver.dead_letter_message(
            message,
            reason="SnykApiError",
            error_description=str(exc),
        )
        return

    _settle_message(message, receiver, result)
    _schedule_followups(result.scheduled_followups, scheduler)


class WorkerConsumer:
    """Long-running worker that consumes queue messages from Service Bus."""

    def __init__(
        self,
        settings: WorkerSettings,
        sync_state: SyncStateStore,
        *,
        sync_deps: WorkerSyncDependencies | None = None,
        credential: Any | None = None,
        client_factory: ServiceBusClientFactory | None = None,
    ) -> None:
        self._settings = settings
        self._sync_state = sync_state
        self._sync_deps = sync_deps
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
        poll_seconds = self._settings.service_bus.receive_max_wait_seconds
        with self._client_factory(
            fully_qualified_namespace=self._settings.service_bus.fully_qualified_namespace,
            credential=self._credential,
        ) as client:
            with client.get_queue_receiver(
                self._settings.service_bus.queue_name,
            ) as receiver, client.get_queue_sender(
                self._settings.service_bus.queue_name,
            ) as sender:
                while True:
                    messages = receiver.receive_messages(
                        max_message_count=1,
                        max_wait_time=poll_seconds,
                    )
                    for message in messages:
                        process_message(
                            message,
                            receiver,
                            settings=self._settings,
                            sync_deps=self._sync_deps,
                            scheduler=sender,
                        )
