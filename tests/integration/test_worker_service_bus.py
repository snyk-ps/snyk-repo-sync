"""Integration tests for worker Service Bus consumption."""

import json
import os
from pathlib import Path

import pytest
from azure.identity import DefaultAzureCredential
from azure.servicebus import ServiceBusClient, ServiceBusMessage

from config.settings import DEFAULT_CONFIG_PATH, load_worker_settings
from worker.consumer import WorkerConsumer, process_message

FIXTURES = Path(__file__).resolve().parents[2] / "data" / "fixtures"

pytestmark = pytest.mark.integration


def _integration_configured() -> bool:
    config_path = os.environ.get("WORKER_CONFIG_PATH", DEFAULT_CONFIG_PATH)
    if not Path(config_path).is_file():
        return False
    try:
        load_worker_settings(config_path)
        return True
    except Exception:
        return False


@pytest.mark.skipif(not _integration_configured(), reason="Worker config not configured")
def test_worker_completes_published_ado_fixture() -> None:
    config_path = os.environ.get("WORKER_CONFIG_PATH", DEFAULT_CONFIG_PATH)
    settings = load_worker_settings(config_path)
    body = (FIXTURES / "eventgrid_ado_default_branch_changed.json").read_text(encoding="utf-8")
    credential = DefaultAzureCredential()

    with ServiceBusClient(
        fully_qualified_namespace=settings.service_bus.fully_qualified_namespace,
        credential=credential,
    ) as client:
        sender = client.get_queue_sender(settings.service_bus.queue_name)
        with sender:
            sender.send_messages(ServiceBusMessage(body))

        receiver = client.get_queue_receiver(settings.service_bus.queue_name, max_wait_time=10)
        with receiver:
            messages = receiver.receive_messages(max_message_count=1, max_wait_time=10)
            assert len(messages) == 1
            process_message(messages[0], receiver)

        receiver = client.get_queue_receiver(settings.service_bus.queue_name, max_wait_time=5)
        with receiver:
            remaining = receiver.receive_messages(max_message_count=1, max_wait_time=2)
            assert remaining == []


@pytest.mark.skipif(not _integration_configured(), reason="Worker config not configured")
def test_worker_completes_published_github_fixture() -> None:
    config_path = os.environ.get("WORKER_CONFIG_PATH", DEFAULT_CONFIG_PATH)
    settings = load_worker_settings(config_path)
    body = (FIXTURES / "github_webhook_created.json").read_text(encoding="utf-8")
    credential = DefaultAzureCredential()

    with ServiceBusClient(
        fully_qualified_namespace=settings.service_bus.fully_qualified_namespace,
        credential=credential,
    ) as client:
        sender = client.get_queue_sender(settings.service_bus.queue_name)
        with sender:
            sender.send_messages(ServiceBusMessage(body))

        receiver = client.get_queue_receiver(settings.service_bus.queue_name, max_wait_time=10)
        with receiver:
            messages = receiver.receive_messages(max_message_count=1, max_wait_time=10)
            assert len(messages) == 1
            message_body = messages[0].body
            if isinstance(message_body, bytes):
                parsed = json.loads(message_body.decode("utf-8"))
            else:
                parsed = json.loads(b"".join(message_body).decode("utf-8"))
            assert parsed["action"] == "created"
            process_message(messages[0], receiver)


@pytest.mark.skipif(not _integration_configured(), reason="Worker config not configured")
def test_worker_consumer_can_be_constructed() -> None:
    from unittest.mock import MagicMock

    config_path = os.environ.get("WORKER_CONFIG_PATH", DEFAULT_CONFIG_PATH)
    settings = load_worker_settings(config_path)
    sync_state = MagicMock()
    sync_state.table_name = settings.sync_state.table_name
    consumer = WorkerConsumer(settings, sync_state, credential=object())
    assert consumer._settings.service_bus.queue_name == settings.service_bus.queue_name
