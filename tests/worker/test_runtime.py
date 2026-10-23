"""Tests for Kafka-mode component supervision."""

import threading

import pytest

from tests.conftest import make_worker_settings
from worker.runtime import KafkaRuntime


class FakeHttpServer:
    """Controllable HTTP component."""

    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.stopped = threading.Event()

    def run(self) -> None:
        if self.fail:
            raise RuntimeError("bind failed")
        self.stopped.wait()

    def stop(self) -> None:
        self.stopped.set()


class FakeFollowUpConsumer:
    """Controllable follow-up component."""

    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.stopped = threading.Event()

    def run(self, *, settings, sync_deps, stop_event: threading.Event) -> None:
        del settings, sync_deps
        if self.fail:
            raise RuntimeError("queue failed")
        stop_event.wait()
        self.stopped.set()


def test_http_failure_stops_followup_consumer() -> None:
    http = FakeHttpServer(fail=True)
    followups = FakeFollowUpConsumer()
    runtime = KafkaRuntime(
        http_server=http,
        followup_consumer=followups,
        settings=make_worker_settings(transport="kafka", service_bus=None),
        sync_deps=None,
    )

    with pytest.raises(RuntimeError, match="HTTP server terminated unexpectedly"):
        runtime.run()

    assert http.stopped.is_set()
    assert followups.stopped.is_set()


def test_followup_failure_stops_http_server() -> None:
    http = FakeHttpServer()
    followups = FakeFollowUpConsumer(fail=True)
    runtime = KafkaRuntime(
        http_server=http,
        followup_consumer=followups,
        settings=make_worker_settings(transport="kafka", service_bus=None),
        sync_deps=None,
    )

    with pytest.raises(
        RuntimeError,
        match="Storage Queue consumer terminated unexpectedly",
    ):
        runtime.run()

    assert http.stopped.is_set()


def test_stop_requests_both_components_to_stop() -> None:
    http = FakeHttpServer()
    followups = FakeFollowUpConsumer()
    runtime = KafkaRuntime(
        http_server=http,
        followup_consumer=followups,
        settings=make_worker_settings(transport="kafka", service_bus=None),
        sync_deps=None,
    )

    runtime.stop()

    assert http.stopped.is_set()
    assert runtime._stop_event.is_set()
