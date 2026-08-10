"""Queue message handling for provider and internal follow-up envelopes."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Literal

from config.scope_mapping import (
    ResolvedScopeMapping,
    ScopeMappingSettings,
    UnmappedScope,
    resolve_scope_mapping,
)
from snyk.client import SnykApiError
from worker.followup import ScheduledFollowUp
from worker.lifecycle import LifecycleOutcome, WorkerSyncDependencies, process_import_poll, process_lifecycle_deferred, process_normalized_event
from worker.message import InboundMessage, MessageParseError, QueueMessage, parse_inbound_message
from worker.normalize import NormalizationError, NormalizedEvent, normalize_ado_audit_record

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class HandleResult:
    """Outcome of queue message handling before settlement."""

    settlement: Literal["complete", "dead_letter"] = "complete"
    dead_letter_reason: str | None = None
    dead_letter_description: str | None = None
    scheduled_followups: tuple[ScheduledFollowUp, ...] = ()
    message: QueueMessage | None = None
    normalized: NormalizedEvent | None = None
    scope_resolution: ResolvedScopeMapping | UnmappedScope | None = None


def handle_queue_message(
    body: str | bytes,
    *,
    scope_mapping: ScopeMappingSettings | None = None,
    sync_deps: WorkerSyncDependencies | None = None,
) -> HandleResult:
    """Parse and process a queue message.

    Args:
        body: Raw queue message body.
        scope_mapping: Optional scope mapping settings from operator config.
        sync_deps: Optional lifecycle sync dependencies for mapped ADO events.

    Returns:
        Settlement instructions and optional scheduled follow-ups.

    Raises:
        MessageParseError: If the message is malformed or unrecognized.
        NormalizationError: If ADO normalization fails.
        SnykApiError: If Snyk API calls fail unrecoverably during lifecycle sync.
    """
    mapping = scope_mapping or ScopeMappingSettings.empty()
    inbound = parse_inbound_message(body)

    if inbound.kind == "internal":
        if sync_deps is None:
            raise MessageParseError("internal follow-up received without sync dependencies")
        assert inbound.internal is not None
        return _handle_internal_message(inbound.internal, deps=sync_deps)

    assert inbound.provider is not None
    message = inbound.provider
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
        return HandleResult(
            message=message,
            normalized=normalized,
            scope_resolution=resolve_scope_mapping(
                mapping,
                source="ado",
                lookup_key=normalized.ado.project_name,
            ),
        )

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

    if sync_deps is None or isinstance(resolution, UnmappedScope):
        return HandleResult(
            message=message,
            normalized=normalized,
            scope_resolution=resolution,
        )

    outcome = process_normalized_event(normalized, resolution, deps=sync_deps)
    return _handle_result_from_outcome(
        outcome,
        message=message,
        normalized=normalized,
        scope_resolution=resolution,
    )


def _handle_internal_message(
    internal,
    *,
    deps: WorkerSyncDependencies,
) -> HandleResult:
    if internal.sync_phase == "import_poll":
        if internal.import_job_id is None or internal.ado_project_name is None:
            raise MessageParseError("import_poll message missing required fields")
        outcome = process_import_poll(
            source=internal.source,
            scope_id=internal.scope_id,
            repository_id=internal.repository_id,
            source_event_id=internal.source_event_id,
            import_job_id=internal.import_job_id,
            retry_count=internal.retry_count,
            ado_project_name=internal.ado_project_name,
            deps=deps,
        )
        return _handle_result_from_outcome(outcome)

    outcome = process_lifecycle_deferred(
        {
            "sourceEventId": internal.source_event_id,
            "eventType": internal.event_type or "",
            "scopeId": internal.scope_id,
            "repositoryId": internal.repository_id,
            "repositoryName": internal.repository_name or "",
            "adoProjectName": internal.ado_project_name or "",
            "defaultBranch": internal.default_branch or "",
            "payload": internal.payload or {},
            "occurredAt": "",
        },
        deps=deps,
    )
    return _handle_result_from_outcome(outcome)


def _handle_result_from_outcome(
    outcome: LifecycleOutcome,
    *,
    message: QueueMessage | None = None,
    normalized: NormalizedEvent | None = None,
    scope_resolution: ResolvedScopeMapping | UnmappedScope | None = None,
) -> HandleResult:
    if outcome.settlement == "dead_letter":
        return HandleResult(
            settlement="dead_letter",
            dead_letter_reason=outcome.dead_letter_reason,
            dead_letter_description=outcome.dead_letter_description,
            scheduled_followups=outcome.scheduled_followups,
            message=message,
            normalized=normalized,
            scope_resolution=scope_resolution,
        )
    return HandleResult(
        scheduled_followups=outcome.scheduled_followups,
        message=message,
        normalized=normalized,
        scope_resolution=scope_resolution,
    )


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
