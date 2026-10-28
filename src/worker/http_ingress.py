"""Private ASGI ingress for connector-pushed GitHub lifecycle events."""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Awaitable, Callable
from typing import Any, Protocol

from config.scope_mapping import ScopeMappingSettings
from config.settings import HttpSettings
from worker.handler import ProcessingOutcome, process_message_body
from worker.lifecycle import WorkerSyncDependencies
from worker.normalize import is_github_parsed_updated_body

logger = logging.getLogger(__name__)

Receive = Callable[[], Awaitable[dict[str, Any]]]
Send = Callable[[dict[str, Any]], Awaitable[None]]


class FollowUpScheduler(Protocol):
    """Schedule durable internal worker follow-ups."""

    def schedule(self, body: dict[str, Any], *, delay_seconds: int) -> None:
        """Schedule one follow-up after the requested delay."""


class _RequestTooLarge(Exception):
    """Raised when an HTTP request exceeds the configured body limit."""


class _FollowUpSchedulingError(Exception):
    """Raised when a required follow-up could not be durably scheduled."""


class GitHubEventsApp:
    """ASGI application for Kafka-mode ``POST /github-events`` ingress."""

    def __init__(
        self,
        settings: HttpSettings,
        *,
        scope_mapping: ScopeMappingSettings,
        sync_deps: WorkerSyncDependencies | None,
        followup_scheduler: FollowUpScheduler,
    ) -> None:
        self._settings = settings
        self._scope_mapping = scope_mapping
        self._sync_deps = sync_deps
        self._followup_scheduler = followup_scheduler
        self._processing_slots = asyncio.Semaphore(settings.processing_concurrency)

    async def __call__(
        self,
        scope: dict[str, Any],
        receive: Receive,
        send: Send,
    ) -> None:
        """Handle one ASGI HTTP request."""
        if scope.get("type") != "http":
            raise ValueError("GitHubEventsApp supports ASGI HTTP scopes only")
        if scope.get("path") != "/github-events":
            await _respond(send, 404)
            return
        if scope.get("method") != "POST":
            await _respond(send, 405)
            return
        if not _is_json_content_type(scope.get("headers", [])):
            await _respond(send, 415)
            return

        try:
            body = await _read_body(
                receive,
                maximum_bytes=self._settings.max_request_body_bytes,
            )
        except _RequestTooLarge:
            await _respond(send, 413)
            return

        boundary_status = _validate_github_boundary(body)
        if boundary_status is not None:
            await _respond(send, boundary_status)
            return

        try:
            async with self._processing_slots:
                outcome = await asyncio.to_thread(self._process_and_schedule, body)
        except _FollowUpSchedulingError as exc:
            logger.error("Failed to schedule HTTP ingress follow-up: %s", exc)
            await _respond(send, 503)
            return
        except Exception:
            logger.exception("Unexpected GitHub HTTP ingress processing failure")
            await _respond(send, 500)
            return

        if outcome.status == "completed":
            await _respond(send, 204)
            return
        await _respond(send, _failure_status(outcome))

    def _process_and_schedule(self, body: bytes) -> ProcessingOutcome:
        outcome = process_message_body(
            body,
            scope_mapping=self._scope_mapping,
            sync_deps=self._sync_deps,
        )
        if outcome.status == "failed":
            return outcome

        assert outcome.result is not None
        try:
            for followup in outcome.result.scheduled_followups:
                self._followup_scheduler.schedule(
                    followup.body,
                    delay_seconds=followup.delay_seconds,
                )
        except Exception as exc:
            raise _FollowUpSchedulingError(str(exc)) from exc
        return outcome


async def _read_body(receive: Receive, *, maximum_bytes: int) -> bytes:
    body = bytearray()
    while True:
        message = await receive()
        if message.get("type") == "http.disconnect":
            return bytes(body)
        if message.get("type") != "http.request":
            continue
        chunk = message.get("body", b"")
        if isinstance(chunk, bytes):
            body.extend(chunk)
        if len(body) > maximum_bytes:
            raise _RequestTooLarge
        if not message.get("more_body", False):
            return bytes(body)


def _is_json_content_type(headers: list[tuple[bytes, bytes]]) -> bool:
    for name, value in headers:
        if name.lower() == b"content-type":
            media_type = value.split(b";", 1)[0].strip().lower()
            return media_type == b"application/json"
    return False


def _validate_github_boundary(body: bytes) -> int | None:
    try:
        data = json.loads(body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return 400
    if not isinstance(data, dict):
        return 400
    if (
        data.get("eventType") == "AzureDevOpsAuditEvent"
        or data.get("subject") == "AzureDevOps/Auditing"
    ):
        return 422
    if is_github_parsed_updated_body(data):
        return None
    action = data.get("action")
    repository = data.get("repository")
    if not isinstance(action, str) or not isinstance(repository, dict):
        return 422
    if action not in {"renamed", "edited", "deleted"}:
        return 422
    return None


def _failure_status(outcome: ProcessingOutcome) -> int:
    if outcome.failure_kind in {"invalid_message", "invalid_normalization"}:
        return 422
    if outcome.failure_kind == "dependency":
        return 503
    return 500


async def _respond(send: Send, status: int) -> None:
    await send(
        {
            "type": "http.response.start",
            "status": status,
            "headers": [(b"content-length", b"0")],
        }
    )
    await send({"type": "http.response.body", "body": b""})
