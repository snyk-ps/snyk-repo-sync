"""Queue message handling for provider and internal follow-up envelopes."""

from __future__ import annotations

import logging
from dataclasses import dataclass, replace
from typing import Literal

from config.errors import ConfigError
from config.scope_mapping import (
    AmbiguousOrgNameMatch,
    PropertyExtractionError,
    ResolvedScopeMapping,
    ScopeMappingSettings,
    UnmappedScope,
    extract_scope_property,
    resolve_scope_mapping,
)
from snyk.client import SnykApiError
from sync_state.entities import RepositoryState
from worker.followup import ScheduledFollowUp
from worker.lifecycle import (
    LifecycleOutcome,
    WorkerSyncDependencies,
    log_scope_resolution,
    process_import_poll,
    process_lifecycle_deferred,
    process_normalized_event,
)
from worker.message import (
    INVALID_MESSAGE_REASON,
    InboundMessage,
    MessageParseError,
    QueueMessage,
    parse_inbound_message,
)
from worker.normalize import (
    INVALID_NORMALIZATION_REASON,
    GitHubNoLifecycleAction,
    NormalizationError,
    NormalizedEvent,
    normalize_ado_audit_record,
    normalize_github_queue_payload,
    scope_lookup_key,
)

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
    scope_resolution: ResolvedScopeMapping | UnmappedScope | AmbiguousOrgNameMatch | None = None


@dataclass(frozen=True)
class ProcessingOutcome:
    """Transport-neutral result of processing one message body."""

    status: Literal["completed", "failed"]
    result: HandleResult | None = None
    failure_kind: Literal[
        "invalid_message",
        "invalid_normalization",
        "configuration",
        "dependency",
        "processing",
    ] | None = None
    reason: str | None = None
    description: str | None = None


def process_message_body(
    body: str | bytes,
    *,
    scope_mapping: ScopeMappingSettings | None = None,
    sync_deps: WorkerSyncDependencies | None = None,
) -> ProcessingOutcome:
    """Process a body and return an outcome independent of its inbound transport."""
    try:
        result = handle_queue_message(
            body,
            scope_mapping=scope_mapping,
            sync_deps=sync_deps,
        )
    except MessageParseError as exc:
        return ProcessingOutcome(
            status="failed",
            failure_kind="invalid_message",
            reason=INVALID_MESSAGE_REASON,
            description=str(exc),
        )
    except NormalizationError as exc:
        return ProcessingOutcome(
            status="failed",
            failure_kind="invalid_normalization",
            reason=INVALID_NORMALIZATION_REASON,
            description=str(exc),
        )
    except ConfigError as exc:
        return ProcessingOutcome(
            status="failed",
            failure_kind="configuration",
            reason="ConfigurationError",
            description=str(exc),
        )
    except SnykApiError as exc:
        return ProcessingOutcome(
            status="failed",
            failure_kind="dependency",
            reason="SnykApiError",
            description=str(exc),
        )

    if result.settlement == "dead_letter":
        return ProcessingOutcome(
            status="failed",
            result=result,
            failure_kind="processing",
            reason=result.dead_letter_reason or "Unknown",
            description=result.dead_letter_description,
        )
    return ProcessingOutcome(status="completed", result=result)


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
        try:
            normalized = normalize_github_queue_payload(
                message.provider_payload,
                delivery_id=message.event_id,
            )
        except GitHubNoLifecycleAction as exc:
            logger.info(
                "GitHub message requires no lifecycle action reason=%s event_id=%s",
                exc,
                message.event_id,
            )
            return HandleResult(message=message)
    else:
        normalized = normalize_ado_audit_record(message.provider_payload)

    raw_body = message.raw_body if message.raw_body is not None else message.provider_payload
    try:
        extracted_value = extract_scope_property(
            mapping,
            source=normalized.source,
            payload=raw_body,
        )
    except PropertyExtractionError as exc:
        raise NormalizationError(str(exc)) from exc
    if extracted_value is not None:
        normalized = replace(normalized, scope_property_value=extracted_value)

    lookup_key = extracted_value if extracted_value is not None else scope_lookup_key(normalized)
    stored_org_id: str | None = None
    stored_integration_type: str | None = None
    if sync_deps is not None:
        existing_state = sync_deps.sync_state.get_repository(
            source=normalized.source,
            scope_id=normalized.scope_id,
            repository_id=normalized.repository_id,
        )
        if isinstance(existing_state, RepositoryState):
            stored_org_id = existing_state.snyk_org_id
            stored_integration_type = existing_state.snyk_integration_type
    resolution = resolve_scope_mapping(
        mapping,
        source=normalized.source,
        lookup_key=scope_lookup_key(normalized),
        extracted_value=extracted_value,
        stored_org_id=stored_org_id,
        stored_integration_type=stored_integration_type,
        group_org_loader=None if sync_deps is None else sync_deps.snyk.list_group_orgs,
    )

    if (
        normalized.event_type == "repo.default_branch_changed"
        and "previousDefaultBranch" not in normalized.payload
        and normalized.source == "ado"
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
            scope_resolution=resolution,
        )

    _log_normalized_event(normalized)
    _log_scope_resolution(normalized, resolution, lookup_key=lookup_key, extracted_value=extracted_value)

    if isinstance(resolution, AmbiguousOrgNameMatch):
        return HandleResult(
            message=message,
            normalized=normalized,
            scope_resolution=resolution,
        )

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


def _log_normalized_event(normalized: NormalizedEvent) -> None:
    if normalized.source == "ado":
        assert normalized.ado is not None
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
        return
    assert normalized.github is not None
    logger.info(
        "Normalized GitHub lifecycle event event_type=%s event_id=%s scope_id=%s "
        "repository_id=%s org_login=%s repository_name=%s payload=%s",
        normalized.event_type,
        normalized.event_id,
        normalized.scope_id,
        normalized.repository_id,
        normalized.github.org_login,
        normalized.repository.name,
        normalized.payload,
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
            scope_lookup_key=internal.ado_project_name,
            extracted_property_value=internal.extracted_property_value,
            deps=deps,
        )
        return _handle_result_from_outcome(outcome)

    outcome = process_lifecycle_deferred(
        {
            "source": internal.source,
            "sourceEventId": internal.source_event_id,
            "eventType": internal.event_type or "",
            "scopeId": internal.scope_id,
            "repositoryId": internal.repository_id,
            "repositoryName": internal.repository_name or "",
            "adoProjectName": internal.ado_project_name or "",
            "defaultBranch": internal.default_branch or "",
            "payload": internal.payload or {},
            "occurredAt": "",
            "extractedPropertyValue": internal.extracted_property_value or "",
        },
        deps=deps,
    )
    return _handle_result_from_outcome(outcome)


def _handle_result_from_outcome(
    outcome: LifecycleOutcome,
    *,
    message: QueueMessage | None = None,
    normalized: NormalizedEvent | None = None,
    scope_resolution: ResolvedScopeMapping | UnmappedScope | AmbiguousOrgNameMatch | None = None,
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
    resolution: ResolvedScopeMapping | UnmappedScope | AmbiguousOrgNameMatch,
    *,
    lookup_key: str,
    extracted_value: str | None,
) -> None:
    log_scope_resolution(
        resolution,
        source=normalized.source,
        lookup_key=lookup_key,
        event_id=normalized.event_id,
        scope_id=normalized.scope_id,
        repository_id=normalized.repository_id,
        extracted_value=extracted_value,
    )
