"""Tests for Service Bus consumer message handling."""

from unittest.mock import MagicMock

from worker.consumer import process_message


class FakeMessage:
    """Minimal stand-in for ServiceBusReceivedMessage."""

    def __init__(self, body: bytes, message_id: str = "msg-1") -> None:
        self.body = body
        self.message_id = message_id


def test_process_message_completes_valid_envelope() -> None:
    body = (
        b'{"source":"ado","ingressId":"id-1","receivedAt":"2026-08-05T18:00:00Z",'
        b'"rawPayload":{"eventType":"git.repo.created"}}'
    )
    message = FakeMessage(body)
    receiver = MagicMock()

    process_message(message, receiver)

    receiver.complete_message.assert_called_once_with(message)
    receiver.dead_letter_message.assert_not_called()


def test_process_message_dead_letters_invalid_envelope() -> None:
    message = FakeMessage(b"{}")
    receiver = MagicMock()

    process_message(message, receiver)

    receiver.dead_letter_message.assert_called_once()
    kwargs = receiver.dead_letter_message.call_args.kwargs
    assert kwargs["reason"] == "InvalidEnvelope"
    receiver.complete_message.assert_not_called()
