"""ADO repository lifecycle sync against Snyk."""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass, field, replace
from typing import Any

from ado.client import AdoClient
from config.ignored_repos import IgnoreMatch, is_ignored
from config.scope_mapping import (
    AmbiguousOrgNameMatch,
    IntegrationSettings,
    ResolvedScopeMapping,
    ScopeMappingSettings,
    ScopeSource,
    UnmappedScope,
    configured_integration_id,
    resolve_integration_settings,
    resolve_scope_mapping,
)
from config.snyk_settings import RemovalMode, SnykSettings
from snyk.client import ImportTarget, SnykApiError, SnykClient
from snyk.integration_resolver import IntegrationResolver
from sync_state.client import SyncStateStore
from sync_state.entities import RepositoryState
from worker.followup import (
    IGNORE_MIGRATION_FAILED_REASON,
    IMPORT_JOB_FAILED_REASON,
    MAX_IMPORT_POLL_RETRIES,
    ScheduledFollowUp,
    build_ignore_migration_message,
    build_import_poll_message,
    build_lifecycle_deferred_message,
    compute_backoff_seconds,
)
from worker.idempotency import (
    compute_desired_state_hash,
    default_branch_for_event,
    default_branch_for_state,
    has_pending_import,
    is_desired_state_current,
    is_duplicate_event,
    parsed_updated_scope_is_current,
)
from worker.ignore_migration import (
    IgnoreMigrationError,
    IgnoreMigrationSnapshot,
    clear_ignore_migration,
    copy_v1_project_ignores,
    empty_migration_fields,
    log_ignore_migration,
    migration_state_fields,
    projects_for_reference,
    resolve_updated_source_target_id,
    retire_migration_source,
    safe_failure_reason,
    snapshot_state_fields,
)
from worker.ignore_policy import IgnorePolicyState
from worker.import_branch import resolve_import_branch
from worker.normalize import NormalizedEvent, owner_name, scope_lookup_key
from worker.project_match import ProjectMatchError
from worker.target_resolve import (
    TargetLookup,
    ensure_snyk_target_id,
    rename_previous_name_resolved,
    target_lookup_for_event,
)

logger = logging.getLogger(__name__)


def log_scope_resolution(
    resolution: ResolvedScopeMapping | UnmappedScope | AmbiguousOrgNameMatch,
    *,
    source: str,
    lookup_key: str,
    event_id: str,
    scope_id: str,
    repository_id: str,
    extracted_value: str | None = None,
) -> None:
    """Log a scope resolution outcome without secrets."""
    extracted = f" extracted_value={extracted_value}" if extracted_value else ""
    if isinstance(resolution, AmbiguousOrgNameMatch):
        logger.warning(
            "scope_mapping_org_name_ambiguous source=%s candidate=%s matched_org_name=%s "
            "event_id=%s scope_id=%s repository_id=%s%s",
            resolution.source,
            resolution.candidate,
            ", ".join(resolution.matched_org_names),
            event_id,
            scope_id,
            repository_id,
            extracted,
        )
        return
    if isinstance(resolution, UnmappedScope):
        logger.warning(
            "scope_mapping_unmapped source=%s lookup_key=%s event_id=%s "
            "scope_id=%s repository_id=%s%s",
            resolution.source,
            lookup_key,
            event_id,
            scope_id,
            repository_id,
            extracted,
        )
        return
    if resolution.resolution == "org_name":
        logger.info(
            "scope_mapping_org_name source=%s candidate=%s matched_org_name=%s "
            "snyk_org_id=%s event_id=%s scope_id=%s repository_id=%s%s",
            source,
            resolution.candidate or lookup_key,
            resolution.matched_org_name or "",
            resolution.snyk_org_id,
            event_id,
            scope_id,
            repository_id,
            extracted,
        )
        return
    if resolution.resolution == "default":
        logger.warning(
            "scope_mapping_default source=%s lookup_key=%s event_id=%s "
            "scope_id=%s repository_id=%s snyk_org_id=%s%s",
            source,
            lookup_key,
            event_id,
            scope_id,
            repository_id,
            resolution.snyk_org_id,
            extracted,
        )
        return
    logger.info(
        "Resolved scope mapping source=%s resolution=%s snyk_org_id=%s "
        "event_id=%s scope_id=%s lookup_key=%s%s",
        source,
        resolution.resolution,
        resolution.snyk_org_id,
        event_id,
        scope_id,
        lookup_key,
        extracted,
    )


@dataclass(frozen=True)
class LifecycleOutcome:
    """Result of lifecycle processing before queue settlement."""

    settlement: str = "complete"
    dead_letter_reason: str | None = None
    dead_letter_description: str | None = None
    scheduled_followups: tuple[ScheduledFollowUp, ...] = ()
    skip_reason: str | None = None


@dataclass(frozen=True)
class WorkerSyncDependencies:
    """Runtime dependencies for lifecycle sync."""

    sync_state: SyncStateStore
    snyk: SnykClient
    ado: AdoClient | None
    integration_resolver: IntegrationResolver
    scope_mapping: ScopeMappingSettings
    snyk_settings: SnykSettings
    ignore_policy_state: IgnorePolicyState | None = None
    repository_locks: tuple = field(
        default_factory=lambda: tuple(threading.RLock() for _ in range(64)),
        repr=False,
        compare=False,
    )
    pending_import_lock: threading.RLock = field(
        default_factory=threading.RLock,
        repr=False,
        compare=False,
    )


def _repository_lock(
    deps: WorkerSyncDependencies,
    *,
    source: str,
    scope_id: str,
    repository_id: str,
):
    key = (source, scope_id, repository_id)
    return deps.repository_locks[hash(key) % len(deps.repository_locks)]


def process_normalized_event(
    event: NormalizedEvent,
    resolution: ResolvedScopeMapping | UnmappedScope | AmbiguousOrgNameMatch,
    *,
    deps: WorkerSyncDependencies,
) -> LifecycleOutcome:
    """Execute lifecycle sync while serializing work for the same repository."""
    with _repository_lock(
        deps,
        source=event.source,
        scope_id=event.scope_id,
        repository_id=event.repository_id,
    ):
        return _process_normalized_event(event, resolution, deps=deps)


def _process_normalized_event(
    event: NormalizedEvent,
    resolution: ResolvedScopeMapping | UnmappedScope | AmbiguousOrgNameMatch,
    *,
    deps: WorkerSyncDependencies,
) -> LifecycleOutcome:
    if isinstance(resolution, AmbiguousOrgNameMatch):
        return LifecycleOutcome(skip_reason="ambiguous_org_name")
    if isinstance(resolution, UnmappedScope):
        extracted = (
            f" extracted_value={event.scope_property_value}"
            if event.scope_property_value
            else ""
        )
        logger.warning(
            "scope_mapping_unmapped source=%s lookup_key=%s event_id=%s "
            "scope_id=%s repository_id=%s%s",
            resolution.source,
            resolution.lookup_key,
            event.event_id,
            event.scope_id,
            event.repository_id,
            extracted,
        )
        return LifecycleOutcome(skip_reason="unmapped_scope")

    if (
        event.event_type == "repo.default_branch_changed"
        and "previousDefaultBranch" not in event.payload
        and event.source == "ado"
    ):
        logger.info(
            "Default branch set with no previous default branch; no sync action needed "
            "event_id=%s scope_id=%s repository_id=%s",
            event.event_id,
            event.scope_id,
            event.repository_id,
        )
        return LifecycleOutcome(skip_reason="no_previous_default_branch")

    state = deps.sync_state.get_repository(
        source=event.source,
        scope_id=event.scope_id,
        repository_id=event.repository_id,
    )
    if is_duplicate_event(state, event.event_id):
        if has_pending_import(state):
            logger.info(
                "Duplicate lifecycle event has pending import; rescheduling poll "
                "event_id=%s repository_id=%s",
                event.event_id,
                event.repository_id,
            )
            followup = _schedule_import_poll(event, state, retry_count=0)
            return LifecycleOutcome(
                scheduled_followups=(followup,),
                skip_reason="duplicate_event_pending_import",
            )
        logger.info(
            "Duplicate lifecycle event skipped event_id=%s repository_id=%s",
            event.event_id,
            event.repository_id,
        )
        return LifecycleOutcome(skip_reason="duplicate_event")

    ignore_match = _evaluate_ignore_policy(event, deps=deps)
    if ignore_match is not None:
        return _handle_ignored_event(
            event,
            state=state,
            resolution=resolution,
            deps=deps,
            ignore_match=ignore_match,
        )

    if event.event_type == "repo.deleted":
        return _handle_repo_deleted(event, state, resolution=resolution, deps=deps)

    desired_hash = _desired_hash_for_event(event, state)
    scope_current = parsed_updated_scope_is_current(
        state,
        parsed_updated_import=event.parsed_updated_import,
        resolved_org_id=resolution.snyk_org_id,
        resolved_integration_type=resolution.integration_type,
    )
    if is_desired_state_current(state, desired_hash) and scope_current:
        logger.info(
            "Desired state already satisfied event_id=%s repository_id=%s",
            event.event_id,
            event.repository_id,
        )
        return LifecycleOutcome(skip_reason="desired_state_current")

    if has_pending_import(state):
        followup = _schedule_import_poll(event, state, retry_count=0)
        return LifecycleOutcome(scheduled_followups=(followup,))

    with deps.pending_import_lock:
        if (
            deps.sync_state.count_pending_imports()
            >= deps.snyk_settings.max_concurrent_pending_imports
        ):
            logger.warning(
                "Pending import limit reached source=%s scope_id=%s repository_id=%s "
                "limit=%s event_type=%s outcome=pending_import_limit_reached",
                event.source,
                event.scope_id,
                event.repository_id,
                deps.snyk_settings.max_concurrent_pending_imports,
                event.event_type,
            )
            body = build_lifecycle_deferred_message(
                source=event.source,
                scope_id=event.scope_id,
                repository_id=event.repository_id,
                source_event_id=event.event_id,
                event_type=event.event_type,
                repository_name=event.repository.name,
                ado_project_name=scope_lookup_key(event),
                default_branch=default_branch_for_event(event),
                payload=dict(event.payload),
                retry_count=0,
                extracted_property_value=event.scope_property_value,
                parsed_updated_import=event.parsed_updated_import,
            )
            return LifecycleOutcome(
                scheduled_followups=(
                    ScheduledFollowUp(
                        body=body,
                        delay_seconds=compute_backoff_seconds(0),
                    ),
                ),
            )

        snapshot = _snapshot_ignore_migration(
            event,
            state,
            resolution=resolution,
            deps=deps,
        )
        return _start_import(
            event,
            resolution=resolution,
            existing=state,
            deps=deps,
            snapshot=snapshot,
        )


def process_import_poll(
    *,
    source: str,
    scope_id: str,
    repository_id: str,
    source_event_id: str,
    import_job_id: str,
    retry_count: int,
    scope_lookup_key: str,
    deps: WorkerSyncDependencies,
    extracted_property_value: str | None = None,
) -> LifecycleOutcome:
    """Poll a pending import while serializing work for the same repository."""
    with _repository_lock(
        deps,
        source=source,
        scope_id=scope_id,
        repository_id=repository_id,
    ):
        return _process_import_poll(
            source=source,
            scope_id=scope_id,
            repository_id=repository_id,
            source_event_id=source_event_id,
            import_job_id=import_job_id,
            retry_count=retry_count,
            scope_lookup_key=scope_lookup_key,
            deps=deps,
            extracted_property_value=extracted_property_value,
        )


def _process_import_poll(
    *,
    source: str,
    scope_id: str,
    repository_id: str,
    source_event_id: str,
    import_job_id: str,
    retry_count: int,
    scope_lookup_key: str,
    deps: WorkerSyncDependencies,
    extracted_property_value: str | None = None,
) -> LifecycleOutcome:
    scope_source: ScopeSource = "github" if source == "github" else "ado"
    existing = deps.sync_state.get_repository(
        source=source,
        scope_id=scope_id,
        repository_id=repository_id,
    )
    resolution = resolve_scope_mapping(
        deps.scope_mapping,
        source=scope_source,
        lookup_key=scope_lookup_key,
        extracted_value=extracted_property_value,
        stored_org_id=existing.snyk_org_id if existing is not None else None,
        stored_integration_type=existing.snyk_integration_type if existing is not None else None,
        group_org_loader=deps.snyk.list_group_orgs,
    )
    log_scope_resolution(
        resolution,
        source=source,
        lookup_key=scope_lookup_key,
        event_id=source_event_id,
        scope_id=scope_id,
        repository_id=repository_id,
        extracted_value=extracted_property_value,
    )
    if isinstance(resolution, AmbiguousOrgNameMatch):
        return LifecycleOutcome(skip_reason="ambiguous_org_name")
    if isinstance(resolution, UnmappedScope):
        return LifecycleOutcome(
            settlement="dead_letter",
            dead_letter_reason=IMPORT_JOB_FAILED_REASON,
            dead_letter_description="Scope mapping missing for import poll follow-up",
        )
    integration_id = _resolve_integration_id_for_scope(
        source=scope_source,
        lookup_key=scope_lookup_key,
        org_id=resolution.snyk_org_id,
        deps=deps,
        extracted_value=extracted_property_value,
        resolution=resolution,
    )
    snyk_org_id = resolution.snyk_org_id
    if retry_count >= MAX_IMPORT_POLL_RETRIES:
        logger.error(
            "Import job exceeded max retries source=%s scope_id=%s repository_id=%s "
            "import_job_id=%s retry_count=%s outcome=import_job_failed",
            source,
            scope_id,
            repository_id,
            import_job_id,
            retry_count,
        )
        deps.sync_state.upsert_repository(
            _failed_state_from_existing(
                existing,
                import_job_id=import_job_id,
                source_event_id=source_event_id,
                resolution=resolution,
            ),
            source=source,
            scope_id=scope_id,
            repository_id=repository_id,
        )
        return LifecycleOutcome(
            settlement="dead_letter",
            dead_letter_reason=IMPORT_JOB_FAILED_REASON,
            dead_letter_description=f"Import job {import_job_id} exceeded max retries",
        )

    try:
        job = deps.snyk.get_import_job(snyk_org_id, integration_id, import_job_id)
    except SnykApiError as exc:
        logger.error(
            "Import job poll failed source=%s scope_id=%s repository_id=%s "
            "import_job_id=%s error=%s outcome=import_poll_failed",
            source,
            scope_id,
            repository_id,
            import_job_id,
            exc,
        )
        followup = ScheduledFollowUp(
            body=build_import_poll_message(
                source=source,
                scope_id=scope_id,
                repository_id=repository_id,
                source_event_id=source_event_id,
                import_job_id=import_job_id,
                import_status="pending",
                retry_count=retry_count + 1,
                ado_project_name=scope_lookup_key,
                extracted_property_value=extracted_property_value,
            ),
            delay_seconds=compute_backoff_seconds(retry_count + 1),
        )
        return LifecycleOutcome(scheduled_followups=(followup,))

    if job.state == "pending":
        logger.info(
            "Import job pending source=%s scope_id=%s repository_id=%s "
            "import_job_id=%s retry_count=%s outcome=import_pending",
            source,
            scope_id,
            repository_id,
            import_job_id,
            retry_count,
        )
        followup = ScheduledFollowUp(
            body=build_import_poll_message(
                source=source,
                scope_id=scope_id,
                repository_id=repository_id,
                source_event_id=source_event_id,
                import_job_id=import_job_id,
                import_status="pending",
                retry_count=retry_count + 1,
                ado_project_name=scope_lookup_key,
                extracted_property_value=extracted_property_value,
            ),
            delay_seconds=compute_backoff_seconds(retry_count + 1),
        )
        return LifecycleOutcome(scheduled_followups=(followup,))

    if job.state == "failed":
        logger.error(
            "Import job failed source=%s scope_id=%s repository_id=%s "
            "import_job_id=%s reason=%s outcome=import_failed",
            source,
            scope_id,
            repository_id,
            import_job_id,
            job.failure_reason,
        )
        deps.sync_state.upsert_repository(
            _failed_state_from_existing(
                existing,
                import_job_id=import_job_id,
                source_event_id=source_event_id,
                resolution=resolution,
            ),
            source=source,
            scope_id=scope_id,
            repository_id=repository_id,
        )
        followup = ScheduledFollowUp(
            body=build_import_poll_message(
                source=source,
                scope_id=scope_id,
                repository_id=repository_id,
                source_event_id=source_event_id,
                import_job_id=import_job_id,
                import_status="failed",
                retry_count=retry_count + 1,
                ado_project_name=scope_lookup_key,
                extracted_property_value=extracted_property_value,
            ),
            delay_seconds=compute_backoff_seconds(retry_count + 1),
        )
        return LifecycleOutcome(scheduled_followups=(followup,))

    if existing is None:
        return LifecycleOutcome(
            settlement="dead_letter",
            dead_letter_reason=IMPORT_JOB_FAILED_REASON,
            dead_letter_description="Repository state missing for import poll follow-up",
        )

    source_type = _snyk_source_type(
        scope_source,
        scope_lookup_key,
        deps,
        extracted_value=extracted_property_value,
        resolution=resolution,
    )
    lookup = TargetLookup(
        owner=scope_lookup_key,
        repo_name=existing.repo_name,
        branch=existing.default_branch,
    )
    target_id = ensure_snyk_target_id(
        snyk_org_id,
        stored_id=existing.snyk_target_id,
        lookup=lookup,
        snyk=deps.snyk,
        source_type=source_type,
    )
    if not target_id:
        logger.info(
            "Import job complete but target unresolved source=%s scope_id=%s repository_id=%s "
            "import_job_id=%s retry_count=%s outcome=target_resolve_pending",
            source,
            scope_id,
            repository_id,
            import_job_id,
            retry_count,
        )
        followup = ScheduledFollowUp(
            body=build_import_poll_message(
                source=source,
                scope_id=scope_id,
                repository_id=repository_id,
                source_event_id=source_event_id,
                import_job_id=import_job_id,
                import_status="pending",
                retry_count=retry_count + 1,
                ado_project_name=scope_lookup_key,
                extracted_property_value=extracted_property_value,
            ),
            delay_seconds=compute_backoff_seconds(retry_count + 1),
        )
        return LifecycleOutcome(scheduled_followups=(followup,))

    final_state = _repository_state(
        resolution,
        repo_name=existing.repo_name,
        snyk_target_id=target_id,
        default_branch=existing.default_branch,
        status="active",
        desired_state_hash=existing.desired_state_hash,
        last_event_id=source_event_id,
        tag_applied=False,
        import_job_id=import_job_id,
        import_status="complete",
        owner_name=existing.owner_name or scope_lookup_key,
        **migration_state_fields(existing),
    )
    deps.sync_state.upsert_repository(
        final_state,
        source=source,
        scope_id=scope_id,
        repository_id=repository_id,
    )
    logger.info(
        "Import complete source=%s scope_id=%s repository_id=%s import_job_id=%s "
        "snyk_target_id=%s tag_applied=false outcome=import_complete",
        source,
        scope_id,
        repository_id,
        import_job_id,
        target_id,
    )
    if (
        existing.ignore_migration_kind in {"rename", "default_branch", "updated"}
        and existing.ignore_migration_status == "pending"
    ):
        followup = ScheduledFollowUp(
            body=build_ignore_migration_message(
                source=source,
                scope_id=scope_id,
                repository_id=repository_id,
                source_event_id=source_event_id,
                retry_count=0,
                ado_project_name=scope_lookup_key,
                extracted_property_value=extracted_property_value,
            ),
            delay_seconds=compute_backoff_seconds(0),
        )
        return LifecycleOutcome(scheduled_followups=(followup,))
    return LifecycleOutcome()


def process_ignore_migration(
    *,
    source: str,
    scope_id: str,
    repository_id: str,
    source_event_id: str,
    retry_count: int,
    scope_lookup_key: str,
    deps: WorkerSyncDependencies,
    extracted_property_value: str | None = None,
) -> LifecycleOutcome:
    """Copy or skip v1 project ignores, then retire the source when required."""
    with _repository_lock(
        deps,
        source=source,
        scope_id=scope_id,
        repository_id=repository_id,
    ):
        return _process_ignore_migration(
            source=source,
            scope_id=scope_id,
            repository_id=repository_id,
            source_event_id=source_event_id,
            retry_count=retry_count,
            scope_lookup_key=scope_lookup_key,
            deps=deps,
            extracted_property_value=extracted_property_value,
        )


def _process_ignore_migration(
    *,
    source: str,
    scope_id: str,
    repository_id: str,
    source_event_id: str,
    retry_count: int,
    scope_lookup_key: str,
    deps: WorkerSyncDependencies,
    extracted_property_value: str | None = None,
) -> LifecycleOutcome:
    state = deps.sync_state.get_repository(
        source=source,
        scope_id=scope_id,
        repository_id=repository_id,
    )
    if not isinstance(state, RepositoryState) or not state.ignore_migration_kind:
        return LifecycleOutcome()
    if state.ignore_migration_status not in {"pending", "complete", "skipped"}:
        return LifecycleOutcome()
    if retry_count >= MAX_IMPORT_POLL_RETRIES:
        log_ignore_migration(
            source=source,
            scope_id=scope_id,
            repository_id=repository_id,
            ignore_migration_kind=state.ignore_migration_kind,
            outcome="failed",
            reason="retry_limit",
        )
        return LifecycleOutcome(
            settlement="dead_letter",
            dead_letter_reason=IGNORE_MIGRATION_FAILED_REASON,
            dead_letter_description="v1 project ignore migration exceeded max retries",
        )

    outcome_name = "skipped" if state.ignore_migration_status == "skipped" else "succeeded"
    if state.ignore_migration_status == "pending":
        try:
            outcome_name = _copy_or_skip_ignores(
                state,
                deps=deps,
                extracted_property_value=extracted_property_value,
            )
        except (SnykApiError, ProjectMatchError, IgnoreMigrationError) as exc:
            log_ignore_migration(
                source=source,
                scope_id=scope_id,
                repository_id=repository_id,
                ignore_migration_kind=state.ignore_migration_kind,
                outcome="failed",
                reason=safe_failure_reason(exc),
            )
            return _reschedule_ignore_migration(
                source=source,
                scope_id=scope_id,
                repository_id=repository_id,
                source_event_id=source_event_id,
                retry_count=retry_count,
                scope_lookup_key=scope_lookup_key,
                extracted_property_value=extracted_property_value,
            )
        state = replace(
            state,
            ignore_migration_status="skipped" if outcome_name == "skipped" else "complete",
        )
        deps.sync_state.upsert_repository(
            state,
            source=source,
            scope_id=scope_id,
            repository_id=repository_id,
        )

    if state.ignore_migration_kind in {"rename", "default_branch"}:
        mode = (
            deps.snyk_settings.target_removal.on_rename
            if state.ignore_migration_kind == "rename"
            else deps.snyk_settings.target_removal.on_default_branch_change
        )
        try:
            retire_migration_source(
                deps.snyk,
                kind=state.ignore_migration_kind,
                mode=mode,
                org_id=state.ignore_source_org_id or (state.snyk_org_id or ""),
                target_id=state.ignore_source_target_id,
                previous_reference=state.ignore_source_target_reference,
            )
        except (SnykApiError, IgnoreMigrationError) as exc:
            log_ignore_migration(
                source=source,
                scope_id=scope_id,
                repository_id=repository_id,
                ignore_migration_kind=state.ignore_migration_kind,
                outcome="failed",
                reason=safe_failure_reason(exc),
            )
            return _reschedule_ignore_migration(
                source=source,
                scope_id=scope_id,
                repository_id=repository_id,
                source_event_id=source_event_id,
                retry_count=retry_count,
                scope_lookup_key=scope_lookup_key,
                extracted_property_value=extracted_property_value,
            )

    deps.sync_state.upsert_repository(
        clear_ignore_migration(state),
        source=source,
        scope_id=scope_id,
        repository_id=repository_id,
    )
    log_ignore_migration(
        source=source,
        scope_id=scope_id,
        repository_id=repository_id,
        ignore_migration_kind=state.ignore_migration_kind,
        outcome=outcome_name,
    )
    return LifecycleOutcome()


def _copy_or_skip_ignores(
    state: RepositoryState,
    *,
    deps: WorkerSyncDependencies,
    extracted_property_value: str | None,
) -> str:
    """Return ``skipped`` or ``succeeded`` without retiring the source."""
    if not deps.snyk_settings.migrate_ignores:
        return "skipped"
    destination_org_id = state.snyk_org_id or ""
    if not destination_org_id or not state.snyk_target_id:
        raise IgnoreMigrationError("destination_target_missing")
    source_org_id = state.ignore_source_org_id or destination_org_id
    source_target_id = state.ignore_source_target_id
    if state.ignore_migration_kind == "updated":
        source_target_id = (
            resolve_updated_source_target_id(
                deps.snyk,
                org_id=destination_org_id,
                ado_project=extracted_property_value or "",
                repo_name=state.repo_name,
                branch=state.default_branch,
            )
            or ""
        )
        source_org_id = destination_org_id
    if not source_target_id:
        return "skipped"
    source_projects = deps.snyk.list_projects_for_target(source_org_id, source_target_id)
    destination_projects = deps.snyk.list_projects_for_target(
        destination_org_id,
        state.snyk_target_id,
    )
    if state.ignore_migration_kind == "default_branch":
        source_projects = projects_for_reference(
            source_projects,
            target_reference=state.ignore_source_target_reference,
            include_deactivated=True,
        )
        destination_projects = projects_for_reference(
            destination_projects,
            target_reference=state.default_branch,
        )
    else:
        source_projects = projects_for_reference(source_projects, target_reference=None)
        destination_projects = projects_for_reference(destination_projects, target_reference=None)
    return copy_v1_project_ignores(
        deps.snyk,
        source_org_id=source_org_id,
        source_projects=source_projects,
        destination_org_id=destination_org_id,
        destination_projects=destination_projects,
        import_branch=state.default_branch,
    )


def _reschedule_ignore_migration(
    *,
    source: str,
    scope_id: str,
    repository_id: str,
    source_event_id: str,
    retry_count: int,
    scope_lookup_key: str,
    extracted_property_value: str | None,
) -> LifecycleOutcome:
    followup = ScheduledFollowUp(
        body=build_ignore_migration_message(
            source=source,
            scope_id=scope_id,
            repository_id=repository_id,
            source_event_id=source_event_id,
            retry_count=retry_count + 1,
            ado_project_name=scope_lookup_key,
            extracted_property_value=extracted_property_value,
        ),
        delay_seconds=compute_backoff_seconds(retry_count + 1),
    )
    return LifecycleOutcome(scheduled_followups=(followup,))


def process_lifecycle_deferred(
    message: dict[str, str | dict[str, str] | int | bool],
    *,
    deps: WorkerSyncDependencies,
) -> LifecycleOutcome:
    """Retry deferred lifecycle work when pending import capacity is available."""
    event = _event_from_deferred_message(message)
    state = deps.sync_state.get_repository(
        source=event.source,
        scope_id=event.scope_id,
        repository_id=event.repository_id,
    )
    resolution = resolve_scope_mapping(
        deps.scope_mapping,
        source=event.source,
        lookup_key=scope_lookup_key(event),
        extracted_value=event.scope_property_value,
        stored_org_id=state.snyk_org_id if state is not None else None,
        stored_integration_type=state.snyk_integration_type if state is not None else None,
        group_org_loader=deps.snyk.list_group_orgs,
    )
    log_scope_resolution(
        resolution,
        source=event.source,
        lookup_key=scope_lookup_key(event),
        event_id=event.event_id,
        scope_id=event.scope_id,
        repository_id=event.repository_id,
        extracted_value=event.scope_property_value,
    )
    if isinstance(resolution, AmbiguousOrgNameMatch):
        return LifecycleOutcome(skip_reason="ambiguous_org_name")
    if isinstance(resolution, UnmappedScope):
        return LifecycleOutcome(skip_reason="unmapped_scope")
    return process_normalized_event(event, resolution, deps=deps)


def _evaluate_ignore_policy(
    event: NormalizedEvent,
    *,
    deps: WorkerSyncDependencies,
) -> IgnoreMatch | None:
    if deps.ignore_policy_state is None or deps.ignore_policy_state.policy is None:
        return None
    owner = owner_name(event)
    return is_ignored(
        deps.ignore_policy_state.policy,
        event_source=event.source,
        owner=owner,
        repo_name=event.repository.name,
    )


def _handle_ignored_event(
    event: NormalizedEvent,
    *,
    state: RepositoryState | None,
    resolution: ResolvedScopeMapping,
    deps: WorkerSyncDependencies,
    ignore_match: IgnoreMatch,
) -> LifecycleOutcome:
    logger.info(
        "Ignored repository lifecycle event skipped source=%s scope_id=%s repository_id=%s "
        "repository_name=%s event_type=%s match_kind=%s match_reason=%s outcome=ignored",
        event.source,
        event.scope_id,
        event.repository_id,
        event.repository.name,
        event.event_type,
        ignore_match.kind,
        ignore_match.reason,
    )

    lookup = target_lookup_for_event(event, state)
    stored_id = state.snyk_target_id if state else ""
    source_type = _snyk_source_type(
        event.source,
        scope_lookup_key(event),
        deps,
        extracted_value=event.scope_property_value,
        resolution=resolution,
    )
    target_id = ensure_snyk_target_id(
        resolution.snyk_org_id,
        stored_id=stored_id,
        lookup=lookup,
        snyk=deps.snyk,
        source_type=source_type,
    )
    mode = deps.snyk_settings.target_removal.on_ignore
    if target_id:
        try:
            _apply_target_removal(
                org_id=resolution.snyk_org_id,
                target_id=target_id,
                mode=mode,
                deps=deps,
            )
        except SnykApiError as exc:
            logger.error(
                "Target removal failed for ignored repository source=%s scope_id=%s "
                "repository_id=%s target_id=%s mode=%s error=%s outcome=target_removal_failed",
                event.source,
                event.scope_id,
                event.repository_id,
                target_id,
                mode,
                exc,
            )
            return LifecycleOutcome(
                settlement="dead_letter",
                dead_letter_reason=IMPORT_JOB_FAILED_REASON,
                dead_letter_description="Snyk target removal failed for ignored repository",
            )

    if state is None:
        return LifecycleOutcome(skip_reason="ignored")

    inactive_state = _repository_state(
        resolution,
        repo_name=event.repository.name,
        snyk_target_id="" if mode == "delete" else (target_id or state.snyk_target_id),
        default_branch=state.default_branch or default_branch_for_event(event),
        status="inactive" if target_id or state.import_status == "complete" else state.status,
        desired_state_hash=compute_desired_state_hash(
            event_type=event.event_type,
            repo_name=event.repository.name,
            default_branch=state.default_branch or default_branch_for_event(event),
            status="inactive" if target_id or state.import_status == "complete" else state.status,
        ),
        last_event_id=event.event_id,
        tag_applied=False,
        import_job_id=state.import_job_id,
        import_status=state.import_status if state.import_status == "pending" else "complete",
        owner_name=owner_name(event),
    )
    deps.sync_state.upsert_repository(
        inactive_state,
        source=event.source,
        scope_id=event.scope_id,
        repository_id=event.repository_id,
    )
    return LifecycleOutcome(skip_reason="ignored")


def _handle_repo_deleted(
    event: NormalizedEvent,
    state: RepositoryState | None,
    *,
    resolution: ResolvedScopeMapping,
    deps: WorkerSyncDependencies,
) -> LifecycleOutcome:
    mode = deps.snyk_settings.target_removal.on_repo_delete
    lookup = target_lookup_for_event(event, state)
    stored_id = state.snyk_target_id if state else ""
    source_type = _snyk_source_type(
        event.source,
        scope_lookup_key(event),
        deps,
        extracted_value=event.scope_property_value,
        resolution=resolution,
    )
    target_id = ensure_snyk_target_id(
        resolution.snyk_org_id,
        stored_id=stored_id,
        lookup=lookup,
        snyk=deps.snyk,
        source_type=source_type,
    )
    removal_failed = False
    if target_id:
        try:
            _apply_target_removal(
                org_id=resolution.snyk_org_id,
                target_id=target_id,
                mode=mode,
                deps=deps,
            )
        except SnykApiError as exc:
            removal_failed = True
            logger.error(
                "Target removal failed on delete source=%s scope_id=%s repository_id=%s "
                "target_id=%s mode=%s error=%s outcome=target_removal_failed",
                event.source,
                event.scope_id,
                event.repository_id,
                target_id,
                mode,
                exc,
            )
    elif stored_id.strip():
        logger.warning(
            "Target id missing and REST lookup failed on delete source=%s scope_id=%s "
            "repository_id=%s outcome=target_resolve_failed",
            event.source,
            event.scope_id,
            event.repository_id,
        )

    if removal_failed:
        return LifecycleOutcome(
            settlement="dead_letter",
            dead_letter_reason=IMPORT_JOB_FAILED_REASON,
            dead_letter_description="Snyk target removal failed for deleted repository",
        )

    inactive_state = _repository_state(
        resolution,
        repo_name=event.repository.name,
        snyk_target_id="" if mode == "delete" else (target_id or ""),
        default_branch=state.default_branch if state else default_branch_for_event(event),
        status="inactive",
        desired_state_hash=compute_desired_state_hash(
            event_type="repo.deleted",
            repo_name=event.repository.name,
            default_branch=state.default_branch if state else default_branch_for_event(event),
            status="inactive",
        ),
        last_event_id=event.event_id,
        tag_applied=False,
        import_job_id=state.import_job_id if state else "",
        import_status="failed" if state and state.import_status == "pending" else "complete",
        owner_name=owner_name(event),
    )
    deps.sync_state.upsert_repository(
        inactive_state,
        source=event.source,
        scope_id=event.scope_id,
        repository_id=event.repository_id,
    )
    logger.info(
        "Repository deleted source=%s scope_id=%s repository_id=%s removal_mode=%s "
        "target_id=%s outcome=inactive",
        event.source,
        event.scope_id,
        event.repository_id,
        mode,
        target_id or "",
    )
    return LifecycleOutcome()


def _start_import(
    event: NormalizedEvent,
    *,
    resolution: ResolvedScopeMapping,
    existing: RepositoryState | None,
    deps: WorkerSyncDependencies,
    snapshot: IgnoreMigrationSnapshot | None = None,
) -> LifecycleOutcome:
    integration_id = _resolve_integration_id(event, resolution, deps)
    import_branch = resolve_import_branch(event, existing, ado=deps.ado)
    desired_hash = compute_desired_state_hash(
        event_type=event.event_type,
        repo_name=event.repository.name,
        default_branch=import_branch,
        status="active",
    )
    lookup_key = scope_lookup_key(event)
    target = ImportTarget(
        owner=owner_name(event),
        name=event.repository.name,
        branch=import_branch,
    )
    try:
        job_id = deps.snyk.start_import(resolution.snyk_org_id, integration_id, target)
    except SnykApiError as exc:
        if (
            configured_integration_id(
                deps.scope_mapping,
                source=event.source,
                lookup_key=lookup_key,
                extracted_value=event.scope_property_value,
            )
            and exc.status_code in {400, 404}
        ):
            integration_id = deps.integration_resolver.refresh(
                org_id=resolution.snyk_org_id,
                integration_type=resolve_integration_settings(
                    deps.scope_mapping,
                    source=event.source,
                    lookup_key=lookup_key,
                    extracted_value=event.scope_property_value,
                ).integration_type,
            )
            job_id = deps.snyk.start_import(resolution.snyk_org_id, integration_id, target)
        else:
            logger.error(
                "Import trigger failed source=%s scope_id=%s repository_id=%s error=%s",
                event.source,
                event.scope_id,
                event.repository_id,
                exc,
            )
            raise

    if snapshot is not None and isinstance(existing, RepositoryState):
        deps.sync_state.upsert_repository(
            replace(existing, **snapshot_state_fields(snapshot)),
            source=event.source,
            scope_id=event.scope_id,
            repository_id=event.repository_id,
        )
    migration_fields = (
        snapshot_state_fields(snapshot) if snapshot is not None else empty_migration_fields()
    )
    pending_state = _repository_state(
        resolution,
        repo_name=event.repository.name,
        snyk_target_id="",
        default_branch=import_branch,
        status="pending",
        desired_state_hash=desired_hash,
        last_event_id=event.event_id,
        tag_applied=False,
        import_job_id=job_id,
        import_status="pending",
        owner_name=owner_name(event),
        **migration_fields,
    )
    deps.sync_state.upsert_repository(
        pending_state,
        source=event.source,
        scope_id=event.scope_id,
        repository_id=event.repository_id,
    )
    logger.info(
        "Import triggered source=%s scope_id=%s repository_id=%s import_job_id=%s "
        "snyk_org_id=%s outcome=import_triggered",
        event.source,
        event.scope_id,
        event.repository_id,
        job_id,
        resolution.snyk_org_id,
    )
    followup = _schedule_import_poll(event, pending_state, retry_count=0)
    return LifecycleOutcome(scheduled_followups=(followup,))


def _snapshot_ignore_migration(
    event: NormalizedEvent,
    state: RepositoryState | None,
    *,
    resolution: ResolvedScopeMapping,
    deps: WorkerSyncDependencies,
) -> IgnoreMigrationSnapshot | None:
    """Capture the migration source before import overwrites target id or branch."""
    if event.parsed_updated_import:
        return IgnoreMigrationSnapshot(kind="updated")
    if event.event_type == "repo.renamed":
        if not rename_previous_name_resolved(event, state):
            logger.info(
                "Rename previous name unknown; skipping target removal before import "
                "source=%s scope_id=%s repository_id=%s outcome=rename_previous_name_unknown",
                event.source,
                event.scope_id,
                event.repository_id,
            )
            return IgnoreMigrationSnapshot(kind="rename")
        lookup = target_lookup_for_event(event, state)
        target_id = _resolve_existing_target_id(event, state, resolution=resolution, deps=deps)
        return IgnoreMigrationSnapshot(
            kind="rename",
            source_org_id=resolution.snyk_org_id if target_id else "",
            source_target_id=target_id or "",
            source_target_reference=lookup.branch,
        )
    if event.event_type == "repo.default_branch_changed":
        target_id = _resolve_existing_target_id(event, state, resolution=resolution, deps=deps)
        previous = _previous_branch_reference(
            event,
            state,
            org_id=resolution.snyk_org_id,
            target_id=target_id or "",
            deps=deps,
        )
        return IgnoreMigrationSnapshot(
            kind="default_branch",
            source_org_id=resolution.snyk_org_id if target_id else "",
            source_target_id=target_id or "",
            source_target_reference=previous,
        )
    return None


def _resolve_existing_target_id(
    event: NormalizedEvent,
    state: RepositoryState | None,
    *,
    resolution: ResolvedScopeMapping,
    deps: WorkerSyncDependencies,
) -> str | None:
    lookup = target_lookup_for_event(event, state)
    stored_id = state.snyk_target_id if isinstance(state, RepositoryState) else ""
    source_type = _snyk_source_type(
        event.source,
        scope_lookup_key(event),
        deps,
        extracted_value=event.scope_property_value,
        resolution=resolution,
    )
    return ensure_snyk_target_id(
        resolution.snyk_org_id,
        stored_id=stored_id,
        lookup=lookup,
        snyk=deps.snyk,
        source_type=source_type,
    )


def _previous_branch_reference(
    event: NormalizedEvent,
    state: RepositoryState | None,
    *,
    org_id: str,
    target_id: str,
    deps: WorkerSyncDependencies,
) -> str:
    payload_previous = str(event.payload.get("previousDefaultBranch", "")).strip()
    if payload_previous:
        return payload_previous
    new_branch = default_branch_for_event(event)
    if isinstance(state, RepositoryState) and state.default_branch.strip():
        stored_branch = state.default_branch.strip()
        if stored_branch != new_branch:
            return stored_branch
    if not target_id:
        return ""
    list_projects = getattr(deps.snyk, "list_projects_for_target", None)
    if not callable(list_projects):
        return ""
    projects = list_projects(org_id, target_id)
    if not isinstance(projects, list):
        return ""
    references = {
        project.target_reference
        for project in projects
        if not project.deactivated and project.target_reference and project.target_reference != new_branch
    }
    if len(references) == 1:
        return next(iter(references))
    return ""


def _apply_target_removal(
    *,
    org_id: str,
    target_id: str,
    mode: RemovalMode,
    deps: WorkerSyncDependencies,
) -> None:
    if mode == "delete":
        deps.snyk.delete_snyk_target(org_id, target_id)
        return
    deactivated = deps.snyk.deactivate_all_projects_for_target(org_id, target_id)
    logger.info(
        "Deactivated Snyk projects for target org_id=%s target_id=%s count=%s",
        org_id,
        target_id,
        deactivated,
    )


def _resolve_integration_id(
    event: NormalizedEvent,
    resolution: ResolvedScopeMapping,
    deps: WorkerSyncDependencies,
) -> str:
    return _resolve_integration_id_for_scope(
        source=event.source,
        lookup_key=scope_lookup_key(event),
        org_id=resolution.snyk_org_id,
        deps=deps,
        extracted_value=event.scope_property_value,
        resolution=resolution,
    )


def _integration_settings_for_resolution(
    resolution: ResolvedScopeMapping,
    deps: WorkerSyncDependencies,
    *,
    source: ScopeSource,
    lookup_key: str,
    extracted_value: str | None,
) -> IntegrationSettings:
    if resolution.integration_type is not None:
        return IntegrationSettings(
            integration_type=resolution.integration_type,
            integration_id=resolution.integration_id,
        )
    return resolve_integration_settings(
        deps.scope_mapping,
        source=source,
        lookup_key=lookup_key,
        extracted_value=extracted_value,
    )


def _resolve_integration_id_for_scope(
    *,
    source: ScopeSource,
    lookup_key: str,
    org_id: str,
    deps: WorkerSyncDependencies,
    extracted_value: str | None = None,
    resolution: ResolvedScopeMapping | None = None,
) -> str:
    if resolution is None:
        integration_settings = resolve_integration_settings(
            deps.scope_mapping,
            source=source,
            lookup_key=lookup_key,
            extracted_value=extracted_value,
        )
    else:
        integration_settings = _integration_settings_for_resolution(
            resolution,
            deps,
            source=source,
            lookup_key=lookup_key,
            extracted_value=extracted_value,
        )
    return deps.integration_resolver.resolve(
        org_id=org_id,
        integration_type=integration_settings.integration_type,
        configured_integration_id=integration_settings.integration_id,
    )


def _snyk_source_type(
    source: ScopeSource,
    lookup_key: str,
    deps: WorkerSyncDependencies,
    *,
    extracted_value: str | None = None,
    resolution: ResolvedScopeMapping | None = None,
) -> str:
    """Return Snyk REST ``source_types`` filter for target lookup."""
    if resolution is not None and resolution.integration_type is not None:
        return resolution.integration_type
    return resolve_integration_settings(
        deps.scope_mapping,
        source=source,
        lookup_key=lookup_key,
        extracted_value=extracted_value,
    ).integration_type


def _repository_state(resolution: ResolvedScopeMapping, **kwargs: Any) -> RepositoryState:
    """Build repository state and persist a successful scope resolution."""
    if resolution.integration_type is not None:
        kwargs["snyk_org_id"] = resolution.snyk_org_id
        kwargs["snyk_integration_type"] = resolution.integration_type
    return RepositoryState(**kwargs)


def _schedule_import_poll(
    event: NormalizedEvent,
    state: RepositoryState,
    *,
    retry_count: int,
) -> ScheduledFollowUp:
    body = build_import_poll_message(
        source=event.source,
        scope_id=event.scope_id,
        repository_id=event.repository_id,
        source_event_id=event.event_id,
        import_job_id=state.import_job_id,
        import_status="pending",
        retry_count=retry_count,
        ado_project_name=scope_lookup_key(event),
        extracted_property_value=event.scope_property_value,
    )
    return ScheduledFollowUp(body=body, delay_seconds=compute_backoff_seconds(retry_count))


def _desired_hash_for_event(
    event: NormalizedEvent,
    existing: RepositoryState | None = None,
) -> str:
    branch = default_branch_for_state(event, existing)
    status = "active"
    return compute_desired_state_hash(
        event_type=event.event_type,
        repo_name=event.repository.name,
        default_branch=branch,
        status=status,
    )


def _failed_state_from_existing(
    existing: RepositoryState | None,
    *,
    import_job_id: str,
    source_event_id: str,
    resolution: ResolvedScopeMapping | None = None,
) -> RepositoryState:
    fields = migration_state_fields(existing)
    if existing is None:
        state = RepositoryState(
            repo_name="",
            snyk_target_id="",
            default_branch="",
            status="pending",
            desired_state_hash="",
            last_event_id=source_event_id,
            tag_applied=False,
            import_job_id=import_job_id,
            import_status="failed",
            **fields,
        )
    else:
        state = RepositoryState(
            repo_name=existing.repo_name,
            snyk_target_id=existing.snyk_target_id,
            default_branch=existing.default_branch,
            status=existing.status,
            desired_state_hash=existing.desired_state_hash,
            last_event_id=source_event_id,
            tag_applied=False,
            import_job_id=import_job_id,
            import_status="failed",
            owner_name=existing.owner_name,
            **fields,
        )
    if resolution is None:
        return state
    return _repository_state(
        resolution,
        repo_name=state.repo_name,
        snyk_target_id=state.snyk_target_id,
        default_branch=state.default_branch,
        status=state.status,
        desired_state_hash=state.desired_state_hash,
        last_event_id=state.last_event_id,
        tag_applied=state.tag_applied,
        import_job_id=state.import_job_id,
        import_status=state.import_status,
        owner_name=state.owner_name,
        **fields,
    )


def _event_from_deferred_message(
    message: dict[str, str | dict[str, str] | int | bool],
) -> NormalizedEvent:
    from datetime import UTC, datetime

    from worker.normalize import AdoScope, GitHubScope, RepositoryRef

    payload_raw = message.get("payload")
    payload = dict(payload_raw) if isinstance(payload_raw, dict) else {}
    occurred_at_raw = message.get("occurredAt")
    occurred_at = (
        datetime.fromisoformat(str(occurred_at_raw).replace("Z", "+00:00"))
        if isinstance(occurred_at_raw, str)
        else datetime.now(tz=UTC)
    )
    source = str(message.get("source", "ado"))
    scope_id = str(message["scopeId"])
    lookup_name = str(message["adoProjectName"])
    extracted_raw = message.get("extractedPropertyValue")
    extracted_value = extracted_raw.strip() if isinstance(extracted_raw, str) else None
    parsed_updated_import = message.get("parsedUpdatedImport") is True
    if source == "github":
        return NormalizedEvent(
            source="github",
            event_id=str(message["sourceEventId"]),
            event_type=str(message["eventType"]),  # type: ignore[arg-type]
            scope_id=scope_id,
            repository_id=str(message["repositoryId"]),
            occurred_at=occurred_at,
            repository=RepositoryRef(name=str(message["repositoryName"])),
            github=GitHubScope(org_login=lookup_name),
            payload={str(key): str(value) for key, value in payload.items()},
            scope_property_value=extracted_value or None,
            parsed_updated_import=parsed_updated_import,
        )
    return NormalizedEvent(
        source="ado",
        event_id=str(message["sourceEventId"]),
        event_type=str(message["eventType"]),  # type: ignore[arg-type]
        scope_id=scope_id,
        repository_id=str(message["repositoryId"]),
        occurred_at=occurred_at,
        repository=RepositoryRef(name=str(message["repositoryName"])),
        ado=AdoScope(
            org_id="",
            org_display_name="",
            project_id=scope_id,
            project_name=lookup_name,
        ),
        payload={str(key): str(value) for key, value in payload.items()},
        scope_property_value=extracted_value or None,
    )
