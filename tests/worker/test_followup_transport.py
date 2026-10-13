"""Tests for the Service Bus follow-up transport adapter."""

import json
from unittest.mock import MagicMock

from worker.followup_transport import ServiceBusFollowUpTransport, message_id_of


def test_message_id_of_prefers_service_bus_id() -> None:
    message = MagicMock(message_id="sb-1", id="storage-1")

    assert message_id_of(message) == "sb-1"


def test_message_id_of_uses_storage_id() -> None:
    message = MagicMock(spec=["id"])
    message.id = "storage-1"

    assert message_id_of(message) == "storage-1"


def test_service_bus_transport_delegates_receive_complete_and_dead_letter() -> None:
    receiver = MagicMock()
    receiver.receive_messages.return_value = ["msg"]
    transport = ServiceBusFollowUpTransport(receiver)

    assert transport.receive(max_wait_seconds=5) == ["msg"]
    receiver.receive_messages.assert_called_once_with(max_message_count=1, max_wait_time=5)

    transport.complete("msg")
    receiver.complete_message.assert_called_once_with("msg")

    transport.dead_letter("msg", reason="InvalidMessage", description="bad")
    receiver.dead_letter_message.assert_called_once_with(
        "msg",
        reason="InvalidMessage",
        error_description="bad",
    )


def test_service_bus_transport_schedules_follow_up() -> None:
    sender = MagicMock()
    transport = ServiceBusFollowUpTransport(MagicMock(), sender)

    transport.schedule({"syncPhase": "import_poll"}, delay_seconds=30)

    sender.schedule_messages.assert_called_once()
    messages = sender.schedule_messages.call_args.args[0]
    raw_body = messages[0].body
    if isinstance(raw_body, str):
        encoded = raw_body.encode("utf-8")
    elif isinstance(raw_body, bytes):
        encoded = raw_body
    else:
        encoded = b"".join(raw_body)
    assert json.loads(encoded) == {"syncPhase": "import_poll"}
    assert sender.schedule_messages.call_args.kwargs["schedule_time_utc"] is not None


def test_service_bus_transport_schedule_without_sender_does_not_raise() -> None:
    transport = ServiceBusFollowUpTransport(MagicMock(), sender=None)

    transport.schedule({"syncPhase": "import_poll"}, delay_seconds=30)
