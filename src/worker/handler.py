"""Slice-4 message handling: parse, normalize, and resolve scope mapping."""

import logging
from dataclasses import dataclass

from config.scope_mapping import (
    ResolvedScopeMapping,
    ScopeMappingSettings,
    UnmappedScope,
    resolve_scope_mapping,
)
from worker.message import MessageParseError, QueueMessage, parse_queue_message
from worker.normalize import NormalizationError, NormalizedEvent, normalize_ado_audit_record

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class HandleResult:
    """Outcome of queue message handling before settlement."""

    message: QueueMessage
    normalized: NormalizedEvent | None = None
    scope_resolution: ResolvedScopeMapping | UnmappedScope | None = None


def _log_scope_resolution(
    normalized: NormalizedEvent,
    resolution: ResolvedScopeMapping | UnmappedScope,
) -> None:
    if isinstance(resolution, UnmappedScope):
        logger.warning(
            "Unmapped scope source=%s lookup_key=%s event_id=%s scope_id=%s",
            resolution.source,
            resolution.lookup_key,
            normalized.event_id,
            normalized.scope_id,
        )
        return

    logger.info(
        "Resolved scope mapping source=ado resolution=%s snyk_org_id=%s "
        "event_id=%s scope_id=%s project_name=%s",
        resolution.resolution,
        resolution.snyk_org_id,
        normalized.event_id,
        normalized.scope_id,
        normalized.ado.project_name,
    )


def handle_queue_message(
    body: str | bytes,
    *,
    scope_mapping: ScopeMappingSettings | None = None,
) -> HandleResult:
    """Parse a native queue message and normalize supported ADO lifecycle events.

    GitHub messages are parsed and passed through without normalization.
    ADO messages resolve scope mapping from operator config; Snyk side effects
    are intentionally omitted in this slice.

    Args:
        body: Raw queue message body.
        scope_mapping: Optional scope mapping settings from operator config.

    Returns:
        Parsed message, optional normalized event, and optional scope resolution.

    Raises:
        MessageParseError: If the message is malformed or unrecognized.
        NormalizationError: If ADO normalization fails.
    """
    mapping = scope_mapping or ScopeMappingSettings.empty()
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

    resolution = resolve_scope_mapping(
        mapping,
        source="ado",
        lookup_key=normalized.ado.project_name,
    )
    _log_scope_resolution(normalized, resolution)

    return HandleResult(
        message=message,
        normalized=normalized,
        scope_resolution=resolution,
    )
