"""Tests for private GitHub events HTTP ingress."""

import asyncio
import json
import threading
import time
from pathlib import Path
from unittest.mock import patch

import pytest

from config.scope_mapping import ScopeMappingSettings
from config.settings import HttpSettings
from worker.followup import ScheduledFollowUp
from worker.handler import HandleResult, ProcessingOutcome
from worker.http_ingress import GitHubEventsApp

FIXTURES = Path(__file__).resolve().parents[2] / "data" / "fixtures"


class FakeScheduler:
    """Record scheduled follow-ups and optionally fail."""

    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.scheduled: list[tuple[dict, int]] = []

    def schedule(self, body: dict, *, delay_seconds: int) -> None:
        if self.fail:
            raise RuntimeError("queue unavailable")
        self.scheduled.append((body, delay_seconds))


async def _request(
    app: GitHubEventsApp,
    body: bytes,
    *,
    method: str = "POST",
    path: str = "/github-events",
    content_type: bytes = b"application/json",
) -> tuple[int, list[tuple[bytes, bytes]], bytes]:
    messages = [{"type": "http.request", "body": body, "more_body": False}]
    sent: list[dict] = []

    async def receive() -> dict:
        return messages.pop(0)

    async def send(message: dict) -> None:
        sent.append(message)

    await app(
        {
            "type": "http",
            "method": method,
            "path": path,
            "headers": [(b"content-type", content_type)],
        },
        receive,
        send,
    )
    start = next(message for message in sent if message["type"] == "http.response.start")
    response_body = b"".join(
        message.get("body", b"")
        for message in sent
        if message["type"] == "http.response.body"
    )
    return start["status"], start["headers"], response_body


def _app(
    *,
    max_request_body_bytes: int = 1048576,
    scheduler: FakeScheduler | None = None,
) -> GitHubEventsApp:
    return GitHubEventsApp(
        HttpSettings(max_request_body_bytes=max_request_body_bytes),
        scope_mapping=ScopeMappingSettings.empty(),
        sync_deps=None,
        followup_scheduler=scheduler or FakeScheduler(),
    )


@pytest.mark.parametrize(
    "fixture_name",
    [
        "github_parsed_renamed.json",
        "github_parsed_edited_branch.json",
        "github_parsed_edited_description.json",
        "github_parsed_deleted.json",
    ],
)
def test_existing_github_fixture_returns_204(fixture_name: str) -> None:
    body = (FIXTURES / fixture_name).read_bytes()

    status, _headers, response_body = asyncio.run(_request(_app(), body))

    assert status == 204
    assert response_body == b""


@pytest.mark.parametrize(
    ("body", "expected_status"),
    [
        (b"not-json", 400),
        (b"[]", 400),
        (json.dumps({"action": "created", "repository": {}}).encode(), 422),
        (json.dumps({"action": "updated", "repository": {}}).encode(), 422),
        (json.dumps({"action": "archived", "repository": {}}).encode(), 422),
        (
            json.dumps(
                {
                    "subject": "AzureDevOps/Auditing",
                    "eventType": "AzureDevOpsAuditEvent",
                    "data": {},
                }
            ).encode(),
            422,
        ),
    ],
)
def test_rejected_payloads_do_not_enter_processing(
    body: bytes,
    expected_status: int,
) -> None:
    with patch("worker.http_ingress.process_message_body") as process:
        status, _headers, _response_body = asyncio.run(_request(_app(), body))

    assert status == expected_status
    process.assert_not_called()


def test_wrong_method_and_path_do_not_enter_processing() -> None:
    body = (FIXTURES / "github_parsed_renamed.json").read_bytes()
    with patch("worker.http_ingress.process_message_body") as process:
        method_status, _headers, _body = asyncio.run(
            _request(_app(), body, method="GET")
        )
        path_status, _headers, _body = asyncio.run(
            _request(_app(), body, path="/other")
        )

    assert method_status == 405
    assert path_status == 404
    process.assert_not_called()


def test_non_json_content_type_returns_415() -> None:
    body = (FIXTURES / "github_parsed_renamed.json").read_bytes()

    status, _headers, _response_body = asyncio.run(
        _request(_app(), body, content_type=b"text/plain")
    )

    assert status == 415


def test_oversized_request_returns_413_without_processing() -> None:
    with patch("worker.http_ingress.process_message_body") as process:
        status, _headers, _response_body = asyncio.run(
            _request(_app(max_request_body_bytes=2), b"{}x")
        )

    assert status == 413
    process.assert_not_called()


def test_followup_is_scheduled_before_204_response() -> None:
    scheduler = FakeScheduler()
    followup = ScheduledFollowUp(
        body={"syncPhase": "import_poll", "retryCount": 0},
        delay_seconds=30,
    )
    outcome = ProcessingOutcome(
        status="completed",
        result=HandleResult(scheduled_followups=(followup,)),
    )
    body = (FIXTURES / "github_parsed_renamed.json").read_bytes()

    with patch("worker.http_ingress.process_message_body", return_value=outcome):
        status, _headers, _response_body = asyncio.run(
            _request(_app(scheduler=scheduler), body)
        )

    assert scheduler.scheduled == [(followup.body, 30)]
    assert status == 204


def test_duplicate_completed_outcome_returns_204() -> None:
    outcome = ProcessingOutcome(status="completed", result=HandleResult())
    body = (FIXTURES / "github_parsed_renamed.json").read_bytes()

    with patch("worker.http_ingress.process_message_body", return_value=outcome):
        status, _headers, _response_body = asyncio.run(_request(_app(), body))

    assert status == 204


def test_followup_scheduling_failure_returns_503() -> None:
    scheduler = FakeScheduler(fail=True)
    followup = ScheduledFollowUp(
        body={"syncPhase": "import_poll", "retryCount": 0},
        delay_seconds=30,
    )
    outcome = ProcessingOutcome(
        status="completed",
        result=HandleResult(scheduled_followups=(followup,)),
    )
    body = (FIXTURES / "github_parsed_renamed.json").read_bytes()

    with patch("worker.http_ingress.process_message_body", return_value=outcome):
        status, _headers, _response_body = asyncio.run(
            _request(_app(scheduler=scheduler), body)
        )

    assert status == 503


@pytest.mark.parametrize(
    ("failure_kind", "expected_status"),
    [
        ("invalid_message", 422),
        ("invalid_normalization", 422),
        ("configuration", 500),
        ("dependency", 503),
        ("processing", 500),
    ],
)
def test_processing_failure_returns_non_2xx(
    failure_kind: str,
    expected_status: int,
) -> None:
    outcome = ProcessingOutcome(
        status="failed",
        failure_kind=failure_kind,  # type: ignore[arg-type]
        reason="test",
    )
    body = (FIXTURES / "github_parsed_renamed.json").read_bytes()

    with patch("worker.http_ingress.process_message_body", return_value=outcome):
        status, _headers, _response_body = asyncio.run(_request(_app(), body))

    assert status == expected_status


def test_processing_concurrency_is_bounded() -> None:
    app = _app()
    body = (FIXTURES / "github_parsed_renamed.json").read_bytes()
    lock = threading.Lock()
    active = 0
    maximum_active = 0

    def process(*_args, **_kwargs) -> ProcessingOutcome:
        nonlocal active, maximum_active
        with lock:
            active += 1
            maximum_active = max(maximum_active, active)
        time.sleep(0.02)
        with lock:
            active -= 1
        return ProcessingOutcome(status="completed", result=HandleResult())

    async def run_requests() -> None:
        await asyncio.gather(_request(app, body), _request(app, body))

    with patch("worker.http_ingress.process_message_body", side_effect=process):
        asyncio.run(run_requests())

    assert maximum_active == 1
