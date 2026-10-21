"""Resolve default branch names for Snyk import payloads."""

from __future__ import annotations

from ado.client import AdoClient
from config.errors import ConfigError
from sync_state.entities import RepositoryState
from worker.idempotency import default_branch_for_state
from worker.normalize import NormalizedEvent


def resolve_import_branch(
    event: NormalizedEvent,
    existing: RepositoryState | None,
    *,
    ado: AdoClient | None,
) -> str:
    """Return the branch name required by the Snyk import API."""
    branch = default_branch_for_state(event, existing)
    if branch:
        return branch
    if event.source == "github":
        raise ValueError("GitHub import requires default branch in event or sync state")
    if ado is None:
        raise ConfigError(
            "ADO default-branch enrichment requires ado.organization and ADO_PAT; "
            "configure scopeMapping.azure-repos and ADO credentials",
        )
    return ado.get_repository_default_branch(event.repository_id)
