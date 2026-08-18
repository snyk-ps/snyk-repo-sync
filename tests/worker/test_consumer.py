"""Tests for Service Bus consumer message handling."""

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from config.settings import ServiceBusSettings
from tests.conftest import make_worker_settings
from worker.consumer import WorkerConsumer, _message_body, process_message

FIXTURES = Path(__file__).resolve().parents[2] / "data" / "fixtures"
SETTINGS = make_worker_settings()


class FakeMessage:
    """Minimal stand-in for ServiceBusReceivedMessage."""

    def __init__(self, body, message_id: str = "msg-1") -> None:
        self.body = body
        self.message_id = message_id


def test_message_body_joins_iterable_chunks() -> None:
    payload = (FIXTURES / "eventgrid_ado_default_branch_changed.json").read_bytes()
    midpoint = len(payload) // 2
    message = FakeMessage(body=(payload[:midpoint], payload[midpoint:]))

    body = _message_body(message)

    assert json.loads(body.decode("utf-8"))["subject"] == "AzureDevOps/Auditing"


def test_message_body_joins_generator_chunks() -> None:
    payload = (FIXTURES / "eventgrid_ado_default_branch_changed.json").read_bytes()
    midpoint = len(payload) // 2

    def chunks():
        yield payload[:midpoint]
        yield payload[midpoint:]

    body = _message_body(FakeMessage(body=chunks()))

    assert json.loads(body.decode("utf-8"))["eventType"] == "AzureDevOpsAuditEvent"


def test_process_message_completes_valid_ado_message() -> None:
    body = (FIXTURES / "eventgrid_ado_default_branch_changed.json").read_bytes()
    message = FakeMessage(body)
    receiver = MagicMock()

    process_message(message, receiver, settings=SETTINGS)

    receiver.complete_message.assert_called_once_with(message)
    receiver.dead_letter_message.assert_not_called()


def test_process_message_completes_valid_github_message() -> None:
    body = (FIXTURES / "github_webhook_created.json").read_bytes()
    message = FakeMessage(body)
    receiver = MagicMock()

    process_message(message, receiver, settings=SETTINGS)

    receiver.complete_message.assert_called_once_with(message)
    receiver.dead_letter_message.assert_not_called()


def test_process_message_dead_letters_invalid_message() -> None:
    message = FakeMessage(b"{}")
    receiver = MagicMock()

    process_message(message, receiver, settings=SETTINGS)

    receiver.dead_letter_message.assert_called_once()
    kwargs = receiver.dead_letter_message.call_args.kwargs
    assert kwargs["reason"] == "InvalidMessage"
    receiver.complete_message.assert_not_called()


def test_process_message_completes_default_branch_changed_without_previous_branch() -> None:
    body = json.dumps(
        {
            "subject": "AzureDevOps/Auditing",
            "eventType": "AzureDevOpsAuditEvent",
            "data": {
                "Id": "911fef54-3e24-4c7a-bdf0-84679380b4c7",
                "ActionId": "Git.RepositoryDefaultBranchChanged",
                "ScopeId": "org",
                "ScopeDisplayName": "org (Organization)",
                "ProjectId": "proj",
                "ProjectName": "proj-name",
                "Timestamp": "2026-08-07T17:50:45.8246565Z",
                "Data": {
                    "RepoId": "repo",
                    "RepoName": "test-repo",
                    "DefaultBranch": "refs/heads/main",
                    "PreviousDefaultBranch": "",
                },
            },
        }
    ).encode("utf-8")
    message = FakeMessage(body)
    receiver = MagicMock()

    process_message(message, receiver, settings=SETTINGS)

    receiver.complete_message.assert_called_once_with(message)
    receiver.dead_letter_message.assert_not_called()


def test_process_message_dead_letters_invalid_normalization() -> None:
    body = (
        b'{"subject":"AzureDevOps/Auditing","eventType":"AzureDevOpsAuditEvent",'
        b'"data":{"ActionId":"Git.RepositoryCreated","ProjectId":"proj-1"}}'
    )
    message = FakeMessage(body)
    receiver = MagicMock()

    process_message(message, receiver, settings=SETTINGS)

    receiver.dead_letter_message.assert_called_once()
    kwargs = receiver.dead_letter_message.call_args.kwargs
    assert kwargs["reason"] == "InvalidNormalization"
    receiver.complete_message.assert_not_called()


class _StopPollingForTest(Exception):
    """Stop the consumer run loop during tests."""


def test_run_continues_polling_when_queue_is_idle() -> None:
    settings = make_worker_settings(
        service_bus=ServiceBusSettings(
            fully_qualified_namespace="example.servicebus.windows.net",
            queue_name="repo-sync-events",
            receive_max_wait_seconds=5,
        ),
    )
    sync_state = MagicMock()
    sync_state.table_name = "SnykSyncState"

    poll_calls = {"count": 0}

    def receive_messages(*, max_message_count: int, max_wait_time: int):
        poll_calls["count"] += 1
        assert max_message_count == 1
        assert max_wait_time == 5
        if poll_calls["count"] >= 3:
            raise _StopPollingForTest
        return []

    receiver = MagicMock()
    receiver.receive_messages = receive_messages
    receiver.__enter__ = MagicMock(return_value=receiver)
    receiver.__exit__ = MagicMock(return_value=False)

    sender = MagicMock()
    sender.__enter__ = MagicMock(return_value=sender)
    sender.__exit__ = MagicMock(return_value=False)

    client = MagicMock()
    client.get_queue_receiver.return_value = receiver
    client.get_queue_sender.return_value = sender
    client.__enter__ = MagicMock(return_value=client)
    client.__exit__ = MagicMock(return_value=False)

    consumer = WorkerConsumer(
        settings,
        sync_state,
        credential=object(),
        client_factory=lambda **kwargs: client,
    )

    with pytest.raises(_StopPollingForTest):
        consumer.run()

    assert poll_calls["count"] == 3
    client.get_queue_receiver.assert_called_once_with("repo-sync-events")
