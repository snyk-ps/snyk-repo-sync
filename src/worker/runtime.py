"""Concurrent runtime supervision for Kafka-mode worker components."""

from __future__ import annotations

import queue
import threading
from dataclasses import dataclass
from typing import Protocol

from config.settings import WorkerSettings
from worker.lifecycle import WorkerSyncDependencies


class HttpServerComponent(Protocol):
    """Long-running HTTP server controlled by the Kafka supervisor."""

    def run(self) -> None:
        """Run until stopped or failed."""

    def stop(self) -> None:
        """Request graceful shutdown."""


class FollowUpConsumerComponent(Protocol):
    """Long-running Storage Queue follow-up consumer."""

    def run(
        self,
        *,
        settings: WorkerSettings,
        sync_deps: WorkerSyncDependencies | None,
        stop_event: threading.Event,
    ) -> None:
        """Consume follow-ups until stopped or failed."""


@dataclass(frozen=True)
class _ComponentExit:
    name: str
    error: BaseException | None


class KafkaRuntime:
    """Supervise HTTP ingress and Storage Queue consumption as one runtime."""

    def __init__(
        self,
        *,
        http_server: HttpServerComponent,
        followup_consumer: FollowUpConsumerComponent,
        settings: WorkerSettings,
        sync_deps: WorkerSyncDependencies | None,
    ) -> None:
        self._http_server = http_server
        self._followup_consumer = followup_consumer
        self._settings = settings
        self._sync_deps = sync_deps
        self._stop_event = threading.Event()

    def run(self) -> None:
        """Run both components and fail if either terminates unexpectedly."""
        exits: queue.Queue[_ComponentExit] = queue.Queue()
        threads = [
            threading.Thread(
                target=self._run_component,
                args=("HTTP server", self._http_server.run, exits),
                name="github-events-http",
                daemon=True,
            ),
            threading.Thread(
                target=self._run_component,
                args=("Storage Queue consumer", self._run_followup_consumer, exits),
                name="storage-queue-followups",
                daemon=True,
            ),
        ]
        for thread in threads:
            thread.start()

        try:
            first_exit = exits.get()
        except KeyboardInterrupt:
            self.stop()
            self._join(threads)
            raise

        self.stop()
        self._join(threads)
        message = f"{first_exit.name} terminated unexpectedly"
        if first_exit.error is not None:
            raise RuntimeError(message) from first_exit.error
        raise RuntimeError(message)

    def stop(self) -> None:
        """Request shutdown of both Kafka-mode components."""
        self._stop_event.set()
        self._http_server.stop()

    def _run_followup_consumer(self) -> None:
        self._followup_consumer.run(
            settings=self._settings,
            sync_deps=self._sync_deps,
            stop_event=self._stop_event,
        )

    @staticmethod
    def _run_component(
        name: str,
        target,
        exits: queue.Queue[_ComponentExit],
    ) -> None:
        error: BaseException | None = None
        try:
            target()
        except BaseException as exc:
            error = exc
        exits.put(_ComponentExit(name=name, error=error))

    @staticmethod
    def _join(threads: list[threading.Thread]) -> None:
        for thread in threads:
            thread.join(timeout=10)
