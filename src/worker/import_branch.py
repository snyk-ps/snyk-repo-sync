"""Resolve default branch names for Snyk import payloads."""

from __future__ import annotations

from ado.client import AdoClient
from sync_state.entities import RepositoryState
from worker.idempotency import default_branch_for_state
from worker.normalize import NormalizedEvent


def resolve_import_branch(
    event: NormalizedEvent,
    existing: RepositoryState | None,
    *,
    ado: AdoClient,
) -> str:
    """Return the branch name required by the Snyk import API."""
    branch = default_branch_for_state(event, existing)
    if branch:
        return branch
    return ado.get_repository_default_branch(event.repository_id)
