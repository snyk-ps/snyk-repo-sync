"""Resolve Snyk target ids from sync state or the Snyk REST Targets API."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Protocol

from snyk.client import SnykClient
from sync_state.entities import RepositoryState
from worker.idempotency import default_branch_for_event, default_branch_for_state
from worker.normalize import NormalizedEvent

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class TargetLookup:
    """Parameters used to locate a Snyk target for an ADO repository."""

    owner: str
    repo_name: str
    branch: str


class TargetResolver(Protocol):
    """Protocol for resolving Snyk target ids."""

    def find_target_id(
        self,
        org_id: str,
        *,
        owner: str,
        repo_name: str,
        branch: str = "",
    ) -> str | None:
        """Return a matching Snyk target id, if one exists."""


def target_lookup_for_event(
    event: NormalizedEvent,
    state: RepositoryState | None,
) -> TargetLookup:
    """Build target lookup parameters from an event and optional sync state."""
    owner = event.ado.project_name
    if event.event_type == "repo.renamed":
        repo_name = str(
            event.payload.get("previousRepoName")
            or (state.repo_name if state else "")
            or event.repository.name
        )
        branch = default_branch_for_state(event, state) or default_branch_for_event(event)
    elif event.event_type == "repo.default_branch_changed":
        repo_name = event.repository.name
        branch = str(
            event.payload.get("previousDefaultBranch")
            or (state.default_branch if state else "")
            or default_branch_for_state(event, state)
            or default_branch_for_event(event)
        )
    else:
        repo_name = (
            state.repo_name
            if state and state.repo_name
            else event.repository.name
        )
        branch = default_branch_for_state(event, state) or default_branch_for_event(event)
    return TargetLookup(owner=owner, repo_name=repo_name, branch=branch)


def ensure_snyk_target_id(
    org_id: str,
    *,
    stored_id: str,
    lookup: TargetLookup,
    snyk: TargetResolver,
) -> str | None:
    """Return a Snyk target id from sync state or REST lookup."""
    normalized = stored_id.strip()
    if normalized:
        return normalized
    target_id = snyk.find_target_id(
        org_id,
        owner=lookup.owner,
        repo_name=lookup.repo_name,
        branch=lookup.branch,
    )
    if target_id:
        logger.info(
            "target_resolved org_id=%s owner=%s repo=%s branch=%s target_id=%s",
            org_id,
            lookup.owner,
            lookup.repo_name,
            lookup.branch,
            target_id,
        )
    else:
        logger.warning(
            "target_resolve_failed org_id=%s owner=%s repo=%s branch=%s",
            org_id,
            lookup.owner,
            lookup.repo_name,
            lookup.branch,
        )
    return target_id
