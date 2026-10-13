"""Tests for the Azure Storage queue follow-up transport."""

import json
from typing import Any
from unittest.mock import patch

import pytest

from config.settings import StorageQueueSettings
from tests.conftest import make_worker_settings
from worker.followup import ScheduledFollowUp, build_import_poll_message
from worker.handler import HandleResult
from worker.storage_queue import (
    MAX_DEQUEUE_COUNT_REASON,
    StorageQueueTransport,
    open_storage_queue_transport,
)

QUEUE_SETTINGS = StorageQueueSettings(
    queue_service_url="https://example.queue.core.windows.net",
    queue_name="repo-sync-followups",
    poison_queue_name="repo-sync-followups-poison",
    receive_max_wait_seconds=5,
    visibility_timeout_seconds=60,
)


class _StopPollingForTest(Exception):
    """Stop the storage-queue run loop during tests."""


class FakeMessage:
    """Minimal stand-in for a storage queue message."""

    def __init__(self, content: str, *, dequeue_count: int = 1, message_id: str = "msg-1") -> None:
        self.content = content
        self.dequeue_count = dequeue_count
        self.id = message_id
        self.pop_receipt = f"pop-{message_id}"


class FakeQueue:
    """Records queue operations without Azure."""

    def __init__(self, messages: list[FakeMessage] | None = None) -> None:
        self.messages = list(messages or [])
        self.sent: list[tuple[str, int | None]] = []
        self.deleted: list[tuple[str, str]] = []
        self.receive_calls: list[dict[str, Any]] = []

    def receive_messages(self, **kwargs: Any) -> list[FakeMessage]:
        self.receive_calls.append(kwargs)
        if not self.messages:
            return []
        return [self.messages.pop(0)]

    def send_message(self, content: str, *, visibility_timeout: int | None = None) -> None:
        self.sent.append((content, visibility_timeout))

    def delete_message(self, message_id: str, pop_receipt: str) -> None:
        self.deleted.append((message_id, pop_receipt))


def _transport(
    queue: FakeQueue | None = None,
    poison: FakeQueue | None = None,
) -> tuple[StorageQueueTransport, FakeQueue, FakeQueue]:
    live = queue or FakeQueue()
    poison_queue = poison or FakeQueue()
    return (
        StorageQueueTransport(QUEUE_SETTINGS, queue_client=live, poison_client=poison_queue),
        live,
        poison_queue,
    )


def test_schedule_hides_message_for_the_delay() -> None:
    transport, queue, _poison = _transport()

    transport.schedule({"syncPhase": "import_poll", "retryCount": 1}, delay_seconds=30)

    assert queue.sent == [
        (json.dumps({"syncPhase": "import_poll", "retryCount": 1}), 30),
    ]


def test_schedule_rejects_delay_past_visibility_maximum() -> None:
    transport, queue, _poison = _transport()

    with pytest.raises(ValueError, match="follow-up delay"):
        transport.schedule({"syncPhase": "import_poll"}, delay_seconds=604801)

    assert queue.sent == []


def test_complete_deletes_the_message() -> None:
    transport, queue, _poison = _transport()
    message = FakeMessage("{}")

    transport.complete(message)

    assert queue.deleted == [("msg-1", "pop-msg-1")]
    assert _poison.sent == []


def test_dead_letter_copies_original_body_then_deletes() -> None:
    transport, queue, poison = _transport()
    message = FakeMessage('{"syncPhase":"import_poll"}')

    transport.dead_letter(message, reason="ImportJobFailed", description="retries exhausted")

    assert poison.sent == [('{"syncPhase":"import_poll"}', None)]
    assert queue.deleted == [("msg-1", "pop-msg-1")]
    assert queue.sent == []


def test_dead_letter_leaves_source_when_poison_send_fails() -> None:
    transport, queue, poison = _transport()

    def fail_send(content: str, *, visibility_timeout: int | None = None) -> None:
        del content, visibility_timeout
        raise RuntimeError("poison unavailable")

    poison.send_message = fail_send
    message = FakeMessage('{"syncPhase":"import_poll"}')

    with pytest.raises(RuntimeError, match="poison unavailable"):
        transport.dead_letter(message, reason="ImportJobFailed")

    assert queue.deleted == []


def test_dequeue_count_exhausted_skips_handling() -> None:
    message = FakeMessage('{"syncPhase":"import_poll"}', dequeue_count=10)
    transport, queue, poison = _transport(FakeQueue([message]))
    settings = make_worker_settings()

    with patch("worker.storage_queue.handle_queue_message") as handle:
        transport.process(message, settings=settings)

    handle.assert_not_called()
    assert poison.sent == [('{"syncPhase":"import_poll"}', None)]
    assert queue.deleted == [("msg-1", "pop-msg-1")]


def test_github_webhook_body_is_invalid_message() -> None:
    body = '{"action":"created","repository":{"id":1}}'
    message = FakeMessage(body)
    transport, _queue, poison = _transport()
    settings = make_worker_settings()

    with patch("worker.storage_queue.handle_queue_message") as handle:
        transport.process(message, settings=settings)

    handle.assert_not_called()
    assert poison.sent == [(body, None)]


def test_import_poll_is_deleted_on_success() -> None:
    body = build_import_poll_message(
        source="github",
        scope_id="acme",
        repository_id="1",
        source_event_id="delivery-1",
        import_job_id="job-1",
        import_status="pending",
        retry_count=0,
        ado_project_name="acme",
    )
    message = FakeMessage(json.dumps(body))
    transport, queue, poison = _transport()
    settings = make_worker_settings()

    with patch(
        "worker.storage_queue.handle_queue_message",
        return_value=HandleResult(),
    ) as handle:
        transport.process(message, settings=settings)

    handle.assert_called_once()
    assert queue.deleted == [("msg-1", "pop-msg-1")]
    assert poison.sent == []


def test_import_poll_schedules_the_same_json_body() -> None:
    body = build_import_poll_message(
        source="github",
        scope_id="acme",
        repository_id="1",
        source_event_id="delivery-1",
        import_job_id="job-1",
        import_status="pending",
        retry_count=1,
        ado_project_name="acme",
    )
    message = FakeMessage(json.dumps({"syncPhase": "import_poll"}))
    transport, queue, _poison = _transport()
    settings = make_worker_settings()
    followup = ScheduledFollowUp(body=body, delay_seconds=30)

    with patch(
        "worker.storage_queue.handle_queue_message",
        return_value=HandleResult(scheduled_followups=(followup,)),
    ):
        transport.process(message, settings=settings)

    assert queue.sent == [(json.dumps(body), 30)]


def test_dead_letter_logs_when_source_delete_fails_after_poison_copy() -> None:
    transport, queue, poison = _transport()

    def fail_delete(message_id: str, pop_receipt: str) -> None:
        del message_id, pop_receipt
        raise RuntimeError("delete failed")

    queue.delete_message = fail_delete
    message = FakeMessage('{"syncPhase":"import_poll"}')

    with pytest.raises(RuntimeError, match="delete failed"):
        transport.dead_letter(message, reason="ImportJobFailed")

    assert poison.sent == [('{"syncPhase":"import_poll"}', None)]


def test_receive_locks_message_for_configured_visibility() -> None:
    transport, queue, _poison = _transport()

    assert transport.receive() == []
    assert queue.receive_calls == [
        {
            "messages_per_page": 1,
            "visibility_timeout": 60,
            "max_messages": 1,
        }
    ]


def test_idle_poll_waits_and_does_not_exit() -> None:
    transport, _queue, _poison = _transport()
    waits: list[float] = []

    def sleep(seconds: float) -> None:
        waits.append(seconds)
        if len(waits) >= 2:
            raise _StopPollingForTest

    with pytest.raises(_StopPollingForTest):
        transport.run(settings=make_worker_settings(), sleep=sleep)

    assert waits == [5, 5]


def test_open_storage_queue_transport_binds_both_queues() -> None:
    class _Credential:
        def get_token(self, *scopes: str, **kwargs: object) -> object:
            del scopes, kwargs
            raise AssertionError("token should not be requested while opening clients")

    transport = open_storage_queue_transport(QUEUE_SETTINGS, credential=_Credential())

    assert transport._queue.queue_name == "repo-sync-followups"
    assert transport._poison.queue_name == "repo-sync-followups-poison"
    assert transport._queue.url.startswith("https://example.queue.core.windows.net/")
    assert "repo-sync-followups-poison" in transport._poison.url
