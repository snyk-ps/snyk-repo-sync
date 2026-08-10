"""Native queue message parsing for provider-specific JSON bodies."""

import json
from dataclasses import dataclass
from typing import Any, Literal

from worker.followup import InternalFollowUpMessage, parse_internal_follow_up

ADO_AUDIT_EVENT_TYPE = "AzureDevOpsAuditEvent"
ADO_AUDIT_SUBJECT = "AzureDevOps/Auditing"

INVALID_MESSAGE_REASON = "InvalidMessage"


class MessageParseError(ValueError):
    """Raised when a queue message cannot be parsed or recognized."""


@dataclass(frozen=True)
class QueueMessage:
    """Parsed Service Bus message with inferred provider source."""

    source: Literal["ado", "github"]
    provider_payload: dict[str, Any]
    event_id: str | None = None


@dataclass(frozen=True)
class InboundMessage:
    """Discriminated union wrapper for provider or internal queue payloads."""

    kind: Literal["provider", "internal"]
    provider: QueueMessage | None = None
    internal: InternalFollowUpMessage | None = None


def _is_ado_message(data: dict[str, Any]) -> bool:
    if data.get("eventType") == ADO_AUDIT_EVENT_TYPE:
        return True
    if data.get("subject") == ADO_AUDIT_SUBJECT:
        return True
    return False


def _is_github_message(data: dict[str, Any]) -> bool:
    repository = data.get("repository")
    action = data.get("action")
    return isinstance(repository, dict) and isinstance(action, str) and bool(action.strip())


def _is_internal_message(data: dict[str, Any]) -> bool:
    sync_phase = data.get("syncPhase")
    return sync_phase in {"import_poll", "lifecycle_deferred"}


def parse_inbound_message(body: str | bytes) -> InboundMessage:
    """Parse a queue message as either an internal follow-up or provider payload."""
    data = _load_json_object(body)
    if _is_internal_message(data):
        try:
            internal = parse_internal_follow_up(data)
        except ValueError as exc:
            raise MessageParseError(str(exc)) from exc
        return InboundMessage(kind="internal", internal=internal)
    return InboundMessage(kind="provider", provider=parse_queue_message(body))


def parse_queue_message(body: str | bytes) -> QueueMessage:
    """Parse a native queue message body and infer provider source.

    ADO messages are Event Grid JSON identified by ``eventType`` or ``subject``.
    GitHub messages are raw webhook JSON with ``repository`` and ``action``.

    Args:
        body: Raw queue message body.

    Returns:
        Parsed queue message with provider payload.

    Raises:
        MessageParseError: If JSON is invalid or the message shape is unrecognized.
    """
    data = _load_json_object(body)

    if _is_ado_message(data):
        audit_record = data.get("data")
        if not isinstance(audit_record, dict):
            raise MessageParseError("ADO message missing audit record in data")

        event_id = audit_record.get("Id")
        if event_id is not None and not isinstance(event_id, str):
            event_id = None

        return QueueMessage(
            source="ado",
            provider_payload=audit_record,
            event_id=event_id.strip() if isinstance(event_id, str) and event_id.strip() else None,
        )

    if _is_github_message(data):
        return QueueMessage(source="github", provider_payload=data)

    raise MessageParseError("unrecognized queue message shape")


def _load_json_object(body: str | bytes) -> dict[str, Any]:
    if isinstance(body, bytes):
        text = body.decode("utf-8")
    else:
        text = body

    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise MessageParseError("message body must be valid JSON") from exc

    if not isinstance(data, dict):
        raise MessageParseError("message body must be a JSON object")
    return data
