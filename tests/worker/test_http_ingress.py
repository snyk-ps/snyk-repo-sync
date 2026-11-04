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


def _header(headers: list[tuple[bytes, bytes]], name: bytes) -> bytes | None:
    for header_name, value in headers:
        if header_name.lower() == name:
            return value
    return None


def _assert_empty_success(
    headers: list[tuple[bytes, bytes]],
    response_body: bytes,
) -> None:
    assert response_body == b""
    assert _header(headers, b"content-length") == b"0"
    assert _header(headers, b"content-type") is None


def _assert_json_failure(
    headers: list[tuple[bytes, bytes]],
    response_body: bytes,
    *,
    failure_kind: str,
    reason: str,
    description: str | None = None,
) -> dict[str, str]:
    assert _header(headers, b"content-type") == b"application/json"
    assert _header(headers, b"content-length") == str(len(response_body)).encode("ascii")
    payload = json.loads(response_body)
    assert payload["failureKind"] == failure_kind
    assert payload["reason"] == reason
    assert isinstance(payload["description"], str)
    if description is not None:
        assert payload["description"] == description
    return payload


def _processing_failure_logs(caplog: pytest.LogCaptureFixture) -> list[str]:
    return [
        record.getMessage()
        for record in caplog.records
        if record.levelname == "ERROR"
        and record.getMessage().startswith("HTTP ingress processing failure ")
    ]


async def _request(
    app: GitHubEventsApp,
    body: bytes,
    *,
    method: str = "POST",
    path: str = "/github-events",
    content_type: bytes = b"application/json",
    extra_headers: list[tuple[bytes, bytes]] | None = None,
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
            "headers": [(b"content-type", content_type), *(extra_headers or [])],
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


def test_parsed_updated_fixture_returns_204() -> None:
    body = (FIXTURES / "github_parsed_updated.json").read_bytes()

    status, headers, response_body = asyncio.run(_request(_app(), body))

    assert status == 204
    _assert_empty_success(headers, response_body)


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

    status, headers, response_body = asyncio.run(_request(_app(), body))

    assert status == 204
    _assert_empty_success(headers, response_body)


@pytest.mark.parametrize(
    ("body", "expected_status", "failure_kind", "reason"),
    [
        (b"not-json", 400, "invalid_message", "InvalidJson"),
        (b"[]", 400, "invalid_message", "InvalidJson"),
        (
            json.dumps({"action": "created", "repository": {}}).encode(),
            422,
            "invalid_message",
            "UnsupportedPayload",
        ),
        (
            json.dumps({"action": "updated", "repository": {}}).encode(),
            422,
            "invalid_message",
            "UnsupportedPayload",
        ),
        (
            json.dumps({"action": "archived", "repository": {}}).encode(),
            422,
            "invalid_message",
            "UnsupportedPayload",
        ),
        (
            json.dumps(
                {
                    "subject": "AzureDevOps/Auditing",
                    "eventType": "AzureDevOpsAuditEvent",
                    "data": {},
                }
            ).encode(),
            422,
            "invalid_message",
            "UnsupportedPayload",
        ),
    ],
)
def test_rejected_payloads_do_not_enter_processing(
    body: bytes,
    expected_status: int,
    failure_kind: str,
    reason: str,
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level("ERROR"), patch(
        "worker.http_ingress.process_message_body"
    ) as process:
        status, headers, response_body = asyncio.run(_request(_app(), body))

    assert status == expected_status
    _assert_json_failure(
        headers,
        response_body,
        failure_kind=failure_kind,
        reason=reason,
    )
    assert _processing_failure_logs(caplog) == []
    process.assert_not_called()


def test_wrong_method_and_path_do_not_enter_processing(
    caplog: pytest.LogCaptureFixture,
) -> None:
    body = (FIXTURES / "github_parsed_renamed.json").read_bytes()
    with caplog.at_level("ERROR"), patch(
        "worker.http_ingress.process_message_body"
    ) as process:
        method_status, method_headers, method_body = asyncio.run(
            _request(_app(), body, method="GET")
        )
        path_status, path_headers, path_body = asyncio.run(
            _request(_app(), body, path="/other")
        )

    assert method_status == 405
    _assert_json_failure(
        method_headers,
        method_body,
        failure_kind="request",
        reason="MethodNotAllowed",
        description="The requested method is not allowed.",
    )
    assert path_status == 404
    _assert_json_failure(
        path_headers,
        path_body,
        failure_kind="request",
        reason="NotFound",
        description="The requested path was not found.",
    )
    assert _processing_failure_logs(caplog) == []
    process.assert_not_called()


def test_non_json_content_type_returns_415() -> None:
    body = (FIXTURES / "github_parsed_renamed.json").read_bytes()

    status, headers, response_body = asyncio.run(
        _request(_app(), body, content_type=b"text/plain")
    )

    assert status == 415
    _assert_json_failure(
        headers,
        response_body,
        failure_kind="request",
        reason="UnsupportedMediaType",
        description="Content-Type must be application/json.",
    )


def test_oversized_request_returns_413_without_processing(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level("ERROR"), patch(
        "worker.http_ingress.process_message_body"
    ) as process:
        status, headers, response_body = asyncio.run(
            _request(_app(max_request_body_bytes=2), b"{}x")
        )

    assert status == 413
    _assert_json_failure(
        headers,
        response_body,
        failure_kind="request",
        reason="RequestTooLarge",
        description="The request body exceeds the configured limit.",
    )
    assert _processing_failure_logs(caplog) == []
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
        status, headers, response_body = asyncio.run(
            _request(_app(scheduler=scheduler), body)
        )

    assert scheduler.scheduled == [(followup.body, 30)]
    assert status == 204
    _assert_empty_success(headers, response_body)


def test_duplicate_completed_outcome_returns_204(
    caplog: pytest.LogCaptureFixture,
) -> None:
    outcome = ProcessingOutcome(status="completed", result=HandleResult())
    body = (FIXTURES / "github_parsed_renamed.json").read_bytes()

    with caplog.at_level("ERROR"), patch(
        "worker.http_ingress.process_message_body", return_value=outcome
    ):
        status, headers, response_body = asyncio.run(_request(_app(), body))

    assert status == 204
    _assert_empty_success(headers, response_body)
    assert _processing_failure_logs(caplog) == []


def test_followup_scheduling_failure_returns_503(
    caplog: pytest.LogCaptureFixture,
) -> None:
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

    with caplog.at_level("ERROR"), patch(
        "worker.http_ingress.process_message_body", return_value=outcome
    ):
        status, headers, response_body = asyncio.run(
            _request(_app(scheduler=scheduler), body)
        )

    assert status == 503
    _assert_json_failure(
        headers,
        response_body,
        failure_kind="dependency",
        reason="FollowUpSchedulingError",
        description="queue unavailable",
    )
    assert "Failed to schedule HTTP ingress follow-up: queue unavailable" in caplog.text
    assert _processing_failure_logs(caplog) == []


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
    caplog: pytest.LogCaptureFixture,
) -> None:
    outcome = ProcessingOutcome(
        status="failed",
        failure_kind=failure_kind,  # type: ignore[arg-type]
        reason="test-reason",
        description="failed detail",
    )
    body = (FIXTURES / "github_parsed_renamed.json").read_bytes()

    with caplog.at_level("ERROR"), patch(
        "worker.http_ingress.process_message_body", return_value=outcome
    ):
        status, headers, response_body = asyncio.run(_request(_app(), body))

    assert status == expected_status
    _assert_json_failure(
        headers,
        response_body,
        failure_kind=failure_kind,
        reason="test-reason",
        description="failed detail",
    )
    assert _processing_failure_logs(caplog) == [
        "HTTP ingress processing failure "
        f"failure_kind={failure_kind} reason=test-reason description=failed detail"
    ]


def test_processing_failure_uses_empty_description_when_absent(
    caplog: pytest.LogCaptureFixture,
) -> None:
    outcome = ProcessingOutcome(
        status="failed",
        failure_kind="processing",
        reason="Unknown",
        description=None,
    )
    body = (FIXTURES / "github_parsed_renamed.json").read_bytes()

    with caplog.at_level("ERROR"), patch(
        "worker.http_ingress.process_message_body", return_value=outcome
    ):
        status, headers, response_body = asyncio.run(_request(_app(), body))

    assert status == 500
    _assert_json_failure(
        headers,
        response_body,
        failure_kind="processing",
        reason="Unknown",
        description="",
    )
    assert _processing_failure_logs(caplog) == [
        "HTTP ingress processing failure "
        "failure_kind=processing reason=Unknown description="
    ]


def test_processing_failure_omits_authorization_header(
    caplog: pytest.LogCaptureFixture,
) -> None:
    secret = "snyk-live-token"
    outcome = ProcessingOutcome(
        status="failed",
        failure_kind="dependency",
        reason="SnykApiError",
        description="Snyk API GET /v1/group/group-id/orgs failed with 401: unauthorized",
    )
    body = (FIXTURES / "github_parsed_renamed.json").read_bytes()

    with caplog.at_level("ERROR"), patch(
        "worker.http_ingress.process_message_body", return_value=outcome
    ):
        status, headers, response_body = asyncio.run(
            _request(
                _app(),
                body,
                extra_headers=[(b"authorization", f"token {secret}".encode())],
            )
        )

    assert status == 503
    _assert_json_failure(
        headers,
        response_body,
        failure_kind="dependency",
        reason="SnykApiError",
        description=outcome.description,
    )
    assert secret not in caplog.text
    assert secret.encode() not in response_body


def test_unexpected_exception_returns_500_without_traceback(
    caplog: pytest.LogCaptureFixture,
) -> None:
    body = (FIXTURES / "github_parsed_renamed.json").read_bytes()

    def explode(*_args: object, **_kwargs: object) -> ProcessingOutcome:
        raise RuntimeError("boom")

    with caplog.at_level("ERROR"), patch(
        "worker.http_ingress.process_message_body", side_effect=explode
    ):
        status, headers, response_body = asyncio.run(_request(_app(), body))

    assert status == 500
    _assert_json_failure(
        headers,
        response_body,
        failure_kind="processing",
        reason="UnexpectedError",
        description="boom",
    )
    assert "Traceback" not in response_body.decode()
    assert "Unexpected GitHub HTTP ingress processing failure" in caplog.text
    assert "Traceback (most recent call last)" in caplog.text
    assert _processing_failure_logs(caplog) == []


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
