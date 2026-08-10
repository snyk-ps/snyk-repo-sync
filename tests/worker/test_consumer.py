"""Tests for Service Bus consumer message handling."""

import json
from pathlib import Path
from unittest.mock import MagicMock

from tests.conftest import make_worker_settings
from worker.consumer import _message_body, process_message

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
