"""Service Bus queue consumer for the worker."""

from __future__ import annotations

import logging
from typing import Any, Protocol

from azure.identity import DefaultAzureCredential
from azure.servicebus import ServiceBusClient, ServiceBusReceivedMessage

from config.errors import ConfigError
from config.settings import WorkerSettings
from snyk.client import SnykApiError
from sync_state import SyncStateStore
from worker.event_source import open_github_event_source
from worker.followup_transport import (
    FollowUpTransport,
    ServiceBusFollowUpTransport,
    message_id_of,
)
from worker.handler import HandleResult, handle_queue_message
from worker.lifecycle import WorkerSyncDependencies
from worker.message import INVALID_MESSAGE_REASON, MessageParseError
from worker.normalize import INVALID_NORMALIZATION_REASON, NormalizationError

logger = logging.getLogger(__name__)


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


def _dead_letter(
    message: Any,
    transport: FollowUpTransport,
    *,
    reason: str,
    description: str | None = None,
) -> None:
    transport.dead_letter(message, reason=reason, description=description)
    logger.error(
        "Dead-lettered queue message message_id=%s reason=%s",
        message_id_of(message),
        reason,
    )


def _settle_message(
    message: Any,
    transport: FollowUpTransport,
    result: HandleResult,
) -> None:
    if result.settlement == "dead_letter":
        _dead_letter(
            message,
            transport,
            reason=result.dead_letter_reason or "Unknown",
            description=result.dead_letter_description,
        )
        return

    transport.complete(message)
    logger.info("Completed queue message message_id=%s", message_id_of(message))


def _schedule_followups(
    followups: tuple[Any, ...],
    transport: FollowUpTransport,
) -> None:
    for followup in followups:
        transport.schedule(followup.body, delay_seconds=followup.delay_seconds)


def process_message(
    message: ServiceBusReceivedMessage,
    transport: FollowUpTransport,
    *,
    settings: WorkerSettings,
    sync_deps: WorkerSyncDependencies | None = None,
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
        _dead_letter(
            message,
            transport,
            reason=INVALID_MESSAGE_REASON,
            description=str(exc),
        )
        return
    except NormalizationError as exc:
        logger.warning("Dead-lettering message with invalid normalization: %s", exc)
        _dead_letter(
            message,
            transport,
            reason=INVALID_NORMALIZATION_REASON,
            description=str(exc),
        )
        return
    except ConfigError as exc:
        logger.error("Dead-lettering message after configuration failure: %s", exc)
        _dead_letter(
            message,
            transport,
            reason="ConfigurationError",
            description=str(exc),
        )
        return
    except SnykApiError as exc:
        logger.error("Dead-lettering message after Snyk API failure: %s", exc)
        _dead_letter(
            message,
            transport,
            reason="SnykApiError",
            description=str(exc),
        )
        return

    _settle_message(message, transport, result)
    _schedule_followups(result.scheduled_followups, transport)


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
        if self._settings.transport == "kafka":
            open_github_event_source()
        service_bus = self._settings.service_bus
        if service_bus is None:
            raise ConfigError("serviceBus settings are required for the serviceBus transport")
        logger.info(
            "Starting worker consumer queue_name=%s namespace=%s table_name=%s",
            service_bus.queue_name,
            service_bus.fully_qualified_namespace,
            self._sync_state.table_name,
        )
        poll_seconds = service_bus.receive_max_wait_seconds
        with self._client_factory(
            fully_qualified_namespace=service_bus.fully_qualified_namespace,
            credential=self._credential,
        ) as client:
            with client.get_queue_receiver(
                service_bus.queue_name,
            ) as receiver, client.get_queue_sender(
                service_bus.queue_name,
            ) as sender:
                transport = ServiceBusFollowUpTransport(receiver, sender)
                while True:
                    messages = transport.receive(max_wait_seconds=poll_seconds)
                    for message in messages:
                        process_message(
                            message,
                            transport,
                            settings=self._settings,
                            sync_deps=self._sync_deps,
                        )
