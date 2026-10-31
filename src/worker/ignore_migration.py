"""Copy v1 project ignores and retire the source after import."""

from __future__ import annotations

import logging
from collections.abc import Callable, Sequence
from dataclasses import dataclass, replace
from typing import Literal

from config.snyk_settings import RemovalMode
from snyk.client import ProjectIgnore, SnykApiError, SnykClient, SnykProject
from sync_state.entities import RepositoryState
from worker.project_match import ProjectMatchError, match_projects

logger = logging.getLogger(__name__)

IgnoreMigrationKind = Literal["rename", "default_branch", "updated"]
MigrationOutcome = Literal["skipped", "succeeded"]


@dataclass(frozen=True)
class IgnoreMigrationSnapshot:
    """Source identity captured before import overwrites repository state."""

    kind: IgnoreMigrationKind
    source_org_id: str = ""
    source_target_id: str = ""
    source_target_reference: str = ""


def snapshot_state_fields(snapshot: IgnoreMigrationSnapshot) -> dict[str, str]:
    """Return repository fields for a pending ignore migration."""
    return {
        "ignore_migration_kind": snapshot.kind,
        "ignore_migration_status": "pending",
        "ignore_source_org_id": snapshot.source_org_id,
        "ignore_source_target_id": snapshot.source_target_id,
        "ignore_source_target_reference": snapshot.source_target_reference,
    }


def empty_migration_fields() -> dict[str, str]:
    """Return empty in-flight ignore migration fields."""
    return {
        "ignore_migration_kind": "",
        "ignore_migration_status": "",
        "ignore_source_org_id": "",
        "ignore_source_target_id": "",
        "ignore_source_target_reference": "",
    }


def migration_state_fields(state: RepositoryState | None) -> dict[str, str]:
    """Return in-flight ignore migration fields, or empty strings."""
    if state is None:
        return empty_migration_fields()
    return {
        "ignore_migration_kind": state.ignore_migration_kind,
        "ignore_migration_status": state.ignore_migration_status,
        "ignore_source_org_id": state.ignore_source_org_id,
        "ignore_source_target_id": state.ignore_source_target_id,
        "ignore_source_target_reference": state.ignore_source_target_reference,
    }


def clear_ignore_migration(state: RepositoryState) -> RepositoryState:
    """Return state with the five in-flight ignore migration properties empty."""
    return replace(
        state,
        ignore_migration_kind="",
        ignore_migration_status="",
        ignore_source_org_id="",
        ignore_source_target_id="",
        ignore_source_target_reference="",
    )


def log_ignore_migration(
    *,
    source: str,
    scope_id: str,
    repository_id: str,
    ignore_migration_kind: str,
    outcome: str,
    reason: str | None = None,
) -> None:
    """Log a project-ignore migration outcome without secrets or ignore text."""
    if outcome == "failed":
        logger.error(
            "Project ignore migration source=%s scope_id=%s repository_id=%s "
            "ignore_migration_kind=%s outcome=%s reason=%s",
            source,
            scope_id,
            repository_id,
            ignore_migration_kind,
            outcome,
            reason or "",
        )
        return
    logger.info(
        "Project ignore migration source=%s scope_id=%s repository_id=%s "
        "ignore_migration_kind=%s outcome=%s",
        source,
        scope_id,
        repository_id,
        ignore_migration_kind,
        outcome,
    )


def safe_failure_reason(exc: Exception) -> str:
    """Return a failure reason that omits response bodies and ignore text."""
    if isinstance(exc, SnykApiError):
        if exc.status_code is not None:
            return f"snyk_api_status_{exc.status_code}"
        return "snyk_api_error"
    if isinstance(exc, ProjectMatchError):
        return "project_match_failed"
    return type(exc).__name__


def resolve_updated_source_target_id(
    snyk: SnykClient,
    *,
    org_id: str,
    ado_project: str,
    repo_name: str,
    branch: str,
) -> str | None:
    """Find the Azure DevOps target for a parsed GitHub updated import."""
    if not org_id.strip() or not ado_project.strip() or not repo_name.strip():
        return None
    return snyk.find_target_id(
        org_id,
        owner=ado_project,
        repo_name=repo_name,
        branch=branch,
        source_type="azure-repos",
    )


def copy_v1_project_ignores(
    snyk: SnykClient,
    *,
    source_org_id: str,
    source_projects: Sequence[SnykProject],
    destination_org_id: str,
    destination_projects: Sequence[SnykProject],
    import_branch: str,
) -> MigrationOutcome:
    """Copy v1 project ignores onto matching destination projects.

    The destination is read first. An issue id and path already present is left
    in place. ``ignoredBy`` and ``created`` are not sent.

    Returns:
        ``skipped`` when no source project has ignores, otherwise ``succeeded``.

    Raises:
        ProjectMatchError: When a source project with ignores has no unique match.
        SnykApiError: When a v1 project-ignore call fails.
    """
    ignores_by_source: dict[str, list[ProjectIgnore]] = {}
    for project in source_projects:
        if project.deactivated:
            continue
        ignores = snyk.list_project_ignores(source_org_id, project.id)
        if ignores:
            ignores_by_source[project.id] = ignores
    if not ignores_by_source:
        return "skipped"
    matches = match_projects(
        source_projects,
        destination_projects,
        import_branch=import_branch,
        source_ids_with_ignores=set(ignores_by_source),
    )
    attempted = False
    for source_id, ignores in ignores_by_source.items():
        destination_id = matches.get(source_id)
        if destination_id is None:
            continue
        snyk.add_missing_project_ignores(destination_org_id, destination_id, ignores)
        attempted = True
    if not attempted:
        return "skipped"
    return "succeeded"


def projects_for_reference(
    projects: Sequence[SnykProject],
    *,
    target_reference: str | None,
) -> list[SnykProject]:
    """Return non-deactivated projects, optionally limited to one branch."""
    selected = [project for project in projects if not project.deactivated]
    if target_reference is None:
        return selected
    return [project for project in selected if project.target_reference == target_reference]


def retire_migration_source(
    snyk: SnykClient,
    *,
    kind: str,
    mode: RemovalMode,
    org_id: str,
    target_id: str,
    previous_reference: str,
) -> None:
    """Retire a rename target or the previous branch's projects.

    A missing target id does not call Snyk. Default-branch ``delete`` deletes
    projects and leaves the target in place. HTTP 404 is treated as already gone.

    Raises:
        SnykApiError: When retirement fails for a reason other than not found.
        IgnoreMigrationError: When a default-branch source reference is unknown.
    """
    if kind not in {"rename", "default_branch"}:
        return
    if not target_id.strip():
        return
    if kind == "default_branch" and not previous_reference.strip():
        raise IgnoreMigrationError("previous_branch_unknown")
    if kind == "rename":
        if mode == "delete":
            _ignore_missing(lambda: snyk.delete_snyk_target(org_id, target_id))
            return
        _ignore_missing(lambda: snyk.deactivate_all_projects_for_target(org_id, target_id))
        return

    projects = snyk.list_projects_for_target(org_id, target_id)
    for project in projects:
        if project.target_reference != previous_reference:
            continue
        project_id = project.id
        if mode == "delete":
            _ignore_missing(lambda project_id=project_id: snyk.delete_project(org_id, project_id))
            continue
        if project.deactivated:
            continue
        _ignore_missing(
            lambda project_id=project_id: snyk.deactivate_project(org_id, project_id)
        )


class IgnoreMigrationError(Exception):
    """Raised when ignore migration cannot finish safely."""


def _ignore_missing(action: Callable[[], object]) -> None:
    try:
        action()
    except SnykApiError as exc:
        if exc.status_code == 404:
            return
        raise
