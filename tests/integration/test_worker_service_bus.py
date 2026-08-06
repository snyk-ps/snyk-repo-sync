"""Integration tests for worker Service Bus consumption."""

import json
import os
from pathlib import Path

import pytest
from azure.servicebus import ServiceBusClient, ServiceBusMessage

from config.service_bus import CONNECTION_STRING_ENV, QUEUE_NAME_ENV, load_service_bus_settings
from worker.consumer import WorkerConsumer, process_message

FIXTURES = Path(__file__).resolve().parents[2] / "data" / "fixtures"

pytestmark = pytest.mark.integration


def _service_bus_configured() -> bool:
    return bool(os.environ.get(CONNECTION_STRING_ENV) and os.environ.get(QUEUE_NAME_ENV))


@pytest.mark.skipif(not _service_bus_configured(), reason="Service Bus env not configured")
def test_worker_completes_published_ado_fixture() -> None:
    settings = load_service_bus_settings()
    body = (FIXTURES / "transport_envelope_ado.json").read_text(encoding="utf-8")

    with ServiceBusClient.from_connection_string(settings.connection_string) as client:
        sender = client.get_queue_sender(settings.queue_name)
        with sender:
            sender.send_messages(ServiceBusMessage(body))

        receiver = client.get_queue_receiver(settings.queue_name, max_wait_time=10)
        with receiver:
            messages = receiver.receive_messages(max_message_count=1, max_wait_time=10)
            assert len(messages) == 1
            process_message(messages[0], receiver)

        receiver = client.get_queue_receiver(settings.queue_name, max_wait_time=5)
        with receiver:
            remaining = receiver.receive_messages(max_message_count=1, max_wait_time=2)
            assert remaining == []


@pytest.mark.skipif(not _service_bus_configured(), reason="Service Bus env not configured")
def test_worker_completes_published_github_fixture() -> None:
    settings = load_service_bus_settings()
    body = (FIXTURES / "transport_envelope_github.json").read_text(encoding="utf-8")

    with ServiceBusClient.from_connection_string(settings.connection_string) as client:
        sender = client.get_queue_sender(settings.queue_name)
        with sender:
            sender.send_messages(ServiceBusMessage(body))

        receiver = client.get_queue_receiver(settings.queue_name, max_wait_time=10)
        with receiver:
            messages = receiver.receive_messages(max_message_count=1, max_wait_time=10)
            assert len(messages) == 1
            envelope_body = messages[0].body
            if isinstance(envelope_body, bytes):
                parsed = json.loads(envelope_body.decode("utf-8"))
            else:
                parsed = json.loads(b"".join(envelope_body).decode("utf-8"))
            assert parsed["source"] == "github"
            process_message(messages[0], receiver)


@pytest.mark.skipif(not _service_bus_configured(), reason="Service Bus env not configured")
def test_worker_consumer_can_be_constructed() -> None:
    settings = load_service_bus_settings()
    consumer = WorkerConsumer(settings)
    assert consumer._settings.queue_name == settings.queue_name
