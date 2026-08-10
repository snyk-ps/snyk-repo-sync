"""ADO repository lifecycle sync against Snyk."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from config.scope_mapping import (
    ResolvedScopeMapping,
    ScopeMappingSettings,
    UnmappedScope,
    configured_integration_id,
    resolve_integration_settings,
    resolve_scope_mapping,
)
from ado.client import AdoClient
from config.snyk_settings import RemovalMode, SnykSettings
from snyk.client import ImportTarget, SnykApiError, SnykClient
from snyk.integration_resolver import IntegrationResolver
from sync_state.client import SyncStateStore
from sync_state.entities import RepositoryState
from worker.followup import (
    IMPORT_JOB_FAILED_REASON,
    MAX_IMPORT_POLL_RETRIES,
    ScheduledFollowUp,
    build_import_poll_message,
    build_lifecycle_deferred_message,
    compute_backoff_seconds,
)
from worker.import_branch import resolve_import_branch
from worker.idempotency import (
    compute_desired_state_hash,
    default_branch_for_event,
    default_branch_for_state,
    has_pending_import,
    is_desired_state_current,
    is_duplicate_event,
)
from worker.normalize import NormalizedEvent
from worker.target_resolve import (
    TargetLookup,
    ensure_snyk_target_id,
    target_lookup_for_event,
)

logger = logging.getLogger(__name__)


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
    ado: AdoClient
    integration_resolver: IntegrationResolver
    scope_mapping: ScopeMappingSettings
    snyk_settings: SnykSettings


def process_normalized_event(
    event: NormalizedEvent,
    resolution: ResolvedScopeMapping | UnmappedScope,
    *,
    deps: WorkerSyncDependencies,
) -> LifecycleOutcome:
    """Execute lifecycle sync for a normalized ADO event."""
    if isinstance(resolution, UnmappedScope):
        logger.warning(
            "Unmapped scope source=%s lookup_key=%s event_id=%s scope_id=%s",
            resolution.source,
            resolution.lookup_key,
            event.event_id,
            event.scope_id,
        )
        return LifecycleOutcome(skip_reason="unmapped_scope")

    if event.event_type == "repo.default_branch_changed" and "previousDefaultBranch" not in event.payload:
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
        logger.info(
            "Duplicate lifecycle event skipped event_id=%s repository_id=%s",
            event.event_id,
            event.repository_id,
        )
        return LifecycleOutcome(skip_reason="duplicate_event")

    if event.event_type == "repo.deleted":
        return _handle_repo_deleted(event, state, resolution=resolution, deps=deps)

    desired_hash = _desired_hash_for_event(event, state)
    if is_desired_state_current(state, desired_hash):
        logger.info(
            "Desired state already satisfied event_id=%s repository_id=%s",
            event.event_id,
            event.repository_id,
        )
        return LifecycleOutcome(skip_reason="desired_state_current")

    if has_pending_import(state):
        followup = _schedule_import_poll(event, state, retry_count=0)
        return LifecycleOutcome(scheduled_followups=(followup,))

    if deps.sync_state.count_pending_imports() >= deps.snyk_settings.max_concurrent_pending_imports:
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
            ado_project_name=event.ado.project_name,
            default_branch=default_branch_for_event(event),
            payload=dict(event.payload),
            retry_count=0,
        )
        return LifecycleOutcome(
            scheduled_followups=(
                ScheduledFollowUp(body=body, delay_seconds=compute_backoff_seconds(0)),
            ),
        )

    if event.event_type in {"repo.renamed", "repo.default_branch_changed"}:
        _remove_existing_target_before_reimport(
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
    )


def process_import_poll(
    *,
    source: str,
    scope_id: str,
    repository_id: str,
    source_event_id: str,
    import_job_id: str,
    retry_count: int,
    ado_project_name: str,
    deps: WorkerSyncDependencies,
) -> LifecycleOutcome:
    """Poll a pending import job and finalize or reschedule."""
    resolution = resolve_scope_mapping(
        deps.scope_mapping,
        source="ado",
        lookup_key=ado_project_name,
    )
    if isinstance(resolution, UnmappedScope):
        return LifecycleOutcome(
            settlement="dead_letter",
            dead_letter_reason=IMPORT_JOB_FAILED_REASON,
            dead_letter_description="Scope mapping missing for import poll follow-up",
        )
    integration_id = _resolve_integration_id_from_project(
        ado_project_name=ado_project_name,
        org_id=resolution.snyk_org_id,
        deps=deps,
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
                deps.sync_state.get_repository(
                    source=source,
                    scope_id=scope_id,
                    repository_id=repository_id,
                ),
                import_job_id=import_job_id,
                source_event_id=source_event_id,
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
                ado_project_name=ado_project_name,
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
                ado_project_name=ado_project_name,
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
                deps.sync_state.get_repository(
                    source=source,
                    scope_id=scope_id,
                    repository_id=repository_id,
                ),
                import_job_id=import_job_id,
                source_event_id=source_event_id,
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
                ado_project_name=ado_project_name,
            ),
            delay_seconds=compute_backoff_seconds(retry_count + 1),
        )
        return LifecycleOutcome(scheduled_followups=(followup,))

    existing = deps.sync_state.get_repository(
        source=source,
        scope_id=scope_id,
        repository_id=repository_id,
    )
    if existing is None:
        return LifecycleOutcome(
            settlement="dead_letter",
            dead_letter_reason=IMPORT_JOB_FAILED_REASON,
            dead_letter_description="Repository state missing for import poll follow-up",
        )

    lookup = TargetLookup(
        owner=ado_project_name,
        repo_name=existing.repo_name,
        branch=existing.default_branch,
    )
    target_id = ensure_snyk_target_id(
        snyk_org_id,
        stored_id=existing.snyk_target_id,
        lookup=lookup,
        snyk=deps.snyk,
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
                ado_project_name=ado_project_name,
            ),
            delay_seconds=compute_backoff_seconds(retry_count + 1),
        )
        return LifecycleOutcome(scheduled_followups=(followup,))

    final_state = RepositoryState(
        repo_name=existing.repo_name,
        snyk_target_id=target_id,
        default_branch=existing.default_branch,
        status="active",
        desired_state_hash=existing.desired_state_hash,
        last_event_id=source_event_id,
        tag_applied=False,
        import_job_id=import_job_id,
        import_status="complete",
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
    return LifecycleOutcome()


def process_lifecycle_deferred(
    message: dict[str, str | dict[str, str] | int],
    *,
    deps: WorkerSyncDependencies,
) -> LifecycleOutcome:
    """Retry deferred lifecycle work when pending import capacity is available."""
    event = _event_from_deferred_message(message)
    resolution = resolve_scope_mapping(
        deps.scope_mapping,
        source="ado",
        lookup_key=event.ado.project_name,
    )
    if isinstance(resolution, UnmappedScope):
        return LifecycleOutcome(skip_reason="unmapped_scope")
    return process_normalized_event(event, resolution, deps=deps)


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
    target_id = ensure_snyk_target_id(
        resolution.snyk_org_id,
        stored_id=stored_id,
        lookup=lookup,
        snyk=deps.snyk,
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

    inactive_state = RepositoryState(
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
) -> LifecycleOutcome:
    integration_id = _resolve_integration_id(event, resolution, deps)
    import_branch = resolve_import_branch(event, existing, ado=deps.ado)
    desired_hash = compute_desired_state_hash(
        event_type=event.event_type,
        repo_name=event.repository.name,
        default_branch=import_branch,
        status="active",
    )
    target = ImportTarget(
        owner=event.ado.project_name,
        name=event.repository.name,
        branch=import_branch,
    )
    try:
        job_id = deps.snyk.start_import(resolution.snyk_org_id, integration_id, target)
    except SnykApiError as exc:
        if (
            configured_integration_id(
                deps.scope_mapping,
                source="ado",
                lookup_key=event.ado.project_name,
            )
            and exc.status_code in {400, 404}
        ):
            integration_id = deps.integration_resolver.refresh(
                org_id=resolution.snyk_org_id,
                integration_type=resolve_integration_settings(
                    deps.scope_mapping,
                    source="ado",
                    lookup_key=event.ado.project_name,
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

    pending_state = RepositoryState(
        repo_name=event.repository.name,
        snyk_target_id="",
        default_branch=import_branch,
        status="pending",
        desired_state_hash=desired_hash,
        last_event_id=event.event_id,
        tag_applied=False,
        import_job_id=job_id,
        import_status="pending",
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


def _remove_existing_target_before_reimport(
    event: NormalizedEvent,
    state: RepositoryState | None,
    *,
    resolution: ResolvedScopeMapping,
    deps: WorkerSyncDependencies,
) -> None:
    lookup = target_lookup_for_event(event, state)
    stored_id = state.snyk_target_id if state else ""
    target_id = ensure_snyk_target_id(
        resolution.snyk_org_id,
        stored_id=stored_id,
        lookup=lookup,
        snyk=deps.snyk,
    )
    if not target_id:
        logger.info(
            "No existing Snyk target to remove before reimport source=%s scope_id=%s "
            "repository_id=%s event_type=%s outcome=target_not_found",
            event.source,
            event.scope_id,
            event.repository_id,
            event.event_type,
        )
        return

    if event.event_type == "repo.renamed":
        mode = deps.snyk_settings.target_removal.on_rename
    else:
        mode = deps.snyk_settings.target_removal.on_default_branch_change
    _apply_target_removal(
        org_id=resolution.snyk_org_id,
        target_id=target_id,
        mode=mode,
        deps=deps,
    )
    logger.info(
        "Existing Snyk target removed before reimport source=%s scope_id=%s repository_id=%s "
        "target_id=%s mode=%s outcome=target_removed",
        event.source,
        event.scope_id,
        event.repository_id,
        target_id,
        mode,
    )


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
    return _resolve_integration_id_from_project(
        ado_project_name=event.ado.project_name,
        org_id=resolution.snyk_org_id,
        deps=deps,
    )


def _resolve_integration_id_from_project(
    *,
    ado_project_name: str,
    org_id: str,
    deps: WorkerSyncDependencies,
) -> str:
    integration_settings = resolve_integration_settings(
        deps.scope_mapping,
        source="ado",
        lookup_key=ado_project_name,
    )
    return deps.integration_resolver.resolve(
        org_id=org_id,
        integration_type=integration_settings.integration_type,
        configured_integration_id=integration_settings.integration_id,
    )


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
        ado_project_name=event.ado.project_name,
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
) -> RepositoryState:
    if existing is None:
        return RepositoryState(
            repo_name="",
            snyk_target_id="",
            default_branch="",
            status="pending",
            desired_state_hash="",
            last_event_id=source_event_id,
            tag_applied=False,
            import_job_id=import_job_id,
            import_status="failed",
        )
    return RepositoryState(
        repo_name=existing.repo_name,
        snyk_target_id=existing.snyk_target_id,
        default_branch=existing.default_branch,
        status=existing.status,
        desired_state_hash=existing.desired_state_hash,
        last_event_id=source_event_id,
        tag_applied=False,
        import_job_id=import_job_id,
        import_status="failed",
    )


def _event_from_deferred_message(message: dict[str, str | dict[str, str] | int]) -> NormalizedEvent:
    from datetime import UTC, datetime

    from worker.normalize import AdoScope, RepositoryRef

    payload_raw = message.get("payload")
    payload = dict(payload_raw) if isinstance(payload_raw, dict) else {}
    occurred_at_raw = message.get("occurredAt")
    occurred_at = (
        datetime.fromisoformat(str(occurred_at_raw).replace("Z", "+00:00"))
        if isinstance(occurred_at_raw, str)
        else datetime.now(tz=UTC)
    )
    return NormalizedEvent(
        source="ado",
        event_id=str(message["sourceEventId"]),
        event_type=str(message["eventType"]),  # type: ignore[arg-type]
        scope_id=str(message["scopeId"]),
        repository_id=str(message["repositoryId"]),
        occurred_at=occurred_at,
        repository=RepositoryRef(name=str(message["repositoryName"])),
        ado=AdoScope(
            org_id="",
            org_display_name="",
            project_id=str(message["scopeId"]),
            project_name=str(message["adoProjectName"]),
        ),
        payload={str(key): str(value) for key, value in payload.items()},
    )
