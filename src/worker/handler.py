"""Slice-3 message handling: parse and normalize ADO lifecycle events."""

import logging
from dataclasses import dataclass

from worker.message import MessageParseError, QueueMessage, parse_queue_message
from worker.normalize import NormalizationError, NormalizedEvent, normalize_ado_audit_record

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class HandleResult:
    """Outcome of queue message handling before settlement."""

    message: QueueMessage
    normalized: NormalizedEvent | None = None


def handle_queue_message(body: str | bytes) -> HandleResult:
    """Parse a native queue message and normalize supported ADO lifecycle events.

    GitHub messages are parsed and passed through without normalization.
    Scope mapping and Snyk side effects are intentionally omitted in this slice.

    Args:
        body: Raw queue message body.

    Returns:
        Parsed message and optional normalized event.

    Raises:
        MessageParseError: If the message is malformed or unrecognized.
        NormalizationError: If ADO normalization fails.
    """
    message = parse_queue_message(body)
    logger.info(
        "Parsed queue message source=%s event_id=%s",
        message.source,
        message.event_id,
    )

    if message.source == "github":
        logger.info("GitHub normalization deferred; completing without lifecycle processing")
        return HandleResult(message=message)

    normalized = normalize_ado_audit_record(message.provider_payload)
    if (
        normalized.event_type == "repo.default_branch_changed"
        and "previousDefaultBranch" not in normalized.payload
    ):
        logger.info(
            "Default branch set with no previous default branch; no sync action needed "
            "event_id=%s scope_id=%s repository_id=%s repository_name=%s default_branch=%s",
            normalized.event_id,
            normalized.scope_id,
            normalized.repository_id,
            normalized.repository.name,
            normalized.payload.get("defaultBranch"),
        )
    else:
        logger.info(
            "Normalized ADO lifecycle event event_type=%s event_id=%s scope_id=%s "
            "repository_id=%s ado_org_id=%s ado_project_name=%s repository_name=%s payload=%s",
            normalized.event_type,
            normalized.event_id,
            normalized.scope_id,
            normalized.repository_id,
            normalized.ado.org_id,
            normalized.ado.project_name,
            normalized.repository.name,
            normalized.payload,
        )
    return HandleResult(message=message, normalized=normalized)
