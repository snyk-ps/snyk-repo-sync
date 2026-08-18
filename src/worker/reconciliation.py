"""Background reconciliation for ignored repositories."""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass

from config.ignored_repos import IgnoredReposSettings, is_ignored
from config.scope_mapping import UnmappedScope, resolve_scope_mapping
from sync_state.client import ActiveRepositoryRow, SyncStateStore
from sync_state.entities import RepositoryState
from worker.idempotency import compute_desired_state_hash
from worker.ignore_policy import IgnorePolicyState
from worker.lifecycle import WorkerSyncDependencies, _apply_target_removal
from worker.target_resolve import TargetLookup, ensure_snyk_target_id

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ReconciliationStats:
    """Summary counters for one reconciliation cycle."""

    scanned: int = 0
    matched: int = 0
    removed: int = 0


def run_reconciliation_cycle(
    *,
    settings: IgnoredReposSettings,
    policy_state: IgnorePolicyState,
    sync_state: SyncStateStore,
    deps: WorkerSyncDependencies,
) -> ReconciliationStats:
    """Reload ignore policy and remove targets for newly ignored active repositories."""
    policy = policy_state.reload(settings.policy_path, sync_state)
    if policy is None:
        return ReconciliationStats()

    stats = ReconciliationStats()
    for row in sync_state.list_active_repositories():
        stats = ReconciliationStats(scanned=stats.scanned + 1, matched=stats.matched, removed=stats.removed)
        owner = row.state.owner_name
        if not owner:
            continue
        match = is_ignored(
            policy,
            event_source=row.source,
            owner=owner,
            repo_name=row.state.repo_name,
        )
        if match is None:
            continue
        stats = ReconciliationStats(
            scanned=stats.scanned,
            matched=stats.matched + 1,
            removed=stats.removed,
        )
        if _remove_ignored_target(row, match_reason=match.reason, deps=deps):
            stats = ReconciliationStats(
                scanned=stats.scanned,
                matched=stats.matched,
                removed=stats.removed + 1,
            )

    logger.info(
        "Ignore reconciliation complete scanned=%s matched=%s removed=%s interval_minutes=%s",
        stats.scanned,
        stats.matched,
        stats.removed,
        settings.reconciliation_interval_minutes,
    )
    return stats


def _remove_ignored_target(
    row: ActiveRepositoryRow,
    *,
    match_reason: str,
    deps: WorkerSyncDependencies,
) -> bool:
    resolution = resolve_scope_mapping(
        deps.scope_mapping,
        source=row.source,
        lookup_key=row.state.owner_name,
    )
    if isinstance(resolution, UnmappedScope):
        logger.warning(
            "Ignored repository has unmapped scope during reconciliation source=%s "
            "owner=%s repository_id=%s match_reason=%s outcome=skipped",
            row.source,
            row.state.owner_name,
            row.repository_id,
            match_reason,
        )
        return False

    lookup = TargetLookup(
        owner=row.state.owner_name,
        repo_name=row.state.repo_name,
        branch=row.state.default_branch,
    )
    target_id = ensure_snyk_target_id(
        resolution.snyk_org_id,
        stored_id=row.state.snyk_target_id,
        lookup=lookup,
        snyk=deps.snyk,
    )
    if not target_id:
        logger.info(
            "Ignored repository has no resolvable target during reconciliation source=%s "
            "repository_id=%s match_reason=%s outcome=no_target",
            row.source,
            row.repository_id,
            match_reason,
        )
        return False

    mode = deps.snyk_settings.target_removal.on_ignore
    try:
        _apply_target_removal(
            org_id=resolution.snyk_org_id,
            target_id=target_id,
            mode=mode,
            deps=deps,
        )
    except Exception as exc:
        logger.error(
            "Ignore reconciliation target removal failed source=%s repository_id=%s "
            "target_id=%s match_reason=%s mode=%s error=%s outcome=removal_failed",
            row.source,
            row.repository_id,
            target_id,
            match_reason,
            mode,
            exc,
        )
        return False

    inactive_state = RepositoryState(
        repo_name=row.state.repo_name,
        snyk_target_id="" if mode == "delete" else target_id,
        default_branch=row.state.default_branch,
        status="inactive",
        desired_state_hash=compute_desired_state_hash(
            event_type="repo.deleted",
            repo_name=row.state.repo_name,
            default_branch=row.state.default_branch,
            status="inactive",
        ),
        last_event_id=row.state.last_event_id,
        tag_applied=False,
        import_job_id=row.state.import_job_id,
        import_status="complete",
        owner_name=row.state.owner_name,
    )
    deps.sync_state.upsert_repository(
        inactive_state,
        source=row.source,
        scope_id=row.scope_id,
        repository_id=row.repository_id,
    )
    logger.info(
        "Ignored repository target removed during reconciliation source=%s repository_id=%s "
        "target_id=%s match_reason=%s mode=%s outcome=inactive",
        row.source,
        row.repository_id,
        target_id,
        match_reason,
        mode,
    )
    return True


class IgnoreReconciliationLoop:
    """Background thread that periodically reconciles ignored repositories."""

    def __init__(
        self,
        *,
        settings: IgnoredReposSettings,
        policy_state: IgnorePolicyState,
        sync_state: SyncStateStore,
        deps: WorkerSyncDependencies,
    ) -> None:
        self._settings = settings
        self._policy_state = policy_state
        self._sync_state = sync_state
        self._deps = deps
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        """Start the reconciliation background thread."""
        if self._thread is not None:
            return
        self._thread = threading.Thread(
            target=self._run,
            name="ignore-reconciliation",
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        """Signal the reconciliation loop to stop."""
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=5)

    def _run(self) -> None:
        interval_seconds = self._settings.reconciliation_interval_minutes * 60
        while not self._stop_event.wait(interval_seconds):
            try:
                run_reconciliation_cycle(
                    settings=self._settings,
                    policy_state=self._policy_state,
                    sync_state=self._sync_state,
                    deps=self._deps,
                )
            except Exception as exc:
                logger.error(
                    "Ignore reconciliation cycle failed error=%s outcome=cycle_failed",
                    exc,
                )
