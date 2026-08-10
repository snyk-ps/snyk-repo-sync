"""Idempotency helpers for repository lifecycle sync."""

from __future__ import annotations

import hashlib

from sync_state.entities import RepositoryState
from worker.normalize import EventType, NormalizedEvent


def compute_desired_state_hash(
    *,
    event_type: EventType,
    repo_name: str,
    default_branch: str,
    status: str,
) -> str:
    """Return a stable hash representing intended repository sync outcome."""
    material = f"{event_type}|{repo_name}|{default_branch}|{status}"
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def is_duplicate_event(state: RepositoryState | None, event_id: str) -> bool:
    """Return whether the incoming event id was already processed."""
    return state is not None and state.last_event_id == event_id


def is_desired_state_current(state: RepositoryState | None, desired_hash: str) -> bool:
    """Return whether repository state already reflects the desired outcome."""
    return (
        state is not None
        and state.desired_state_hash == desired_hash
        and state.import_status == "complete"
    )


def has_pending_import(state: RepositoryState | None) -> bool:
    """Return whether a repository already has an in-flight import job."""
    return state is not None and state.import_status == "pending" and bool(state.import_job_id)


def default_branch_for_event(event: NormalizedEvent) -> str:
    """Return the default branch explicitly carried by an event payload."""
    branch = event.payload.get("defaultBranch")
    if isinstance(branch, str) and branch.strip():
        return branch.strip()
    return ""


def default_branch_for_state(
    event: NormalizedEvent,
    existing: RepositoryState | None,
) -> str:
    """Return known default branch from the event or existing sync state."""
    branch = default_branch_for_event(event)
    if branch:
        return branch
    if existing is not None and existing.default_branch.strip():
        return existing.default_branch.strip()
    return ""
