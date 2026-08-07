"""Normalize transport envelopes into provider-neutral lifecycle events."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal

from worker.envelope import TransportEnvelope

INVALID_NORMALIZATION_REASON = "InvalidNormalization"

EventType = Literal[
    "repo.created",
    "repo.renamed",
    "repo.deleted",
    "repo.default_branch_changed",
]

ADO_ACTION_TO_EVENT_TYPE: dict[str, EventType] = {
    "Git.RepositoryCreated": "repo.created",
    "Git.RepositoryRenamed": "repo.renamed",
    "Git.RepositoryDeleted": "repo.deleted",
    "Git.RepositoryDefaultBranchChanged": "repo.default_branch_changed",
}

BRANCH_REF_PREFIX = "refs/heads/"


class NormalizationError(ValueError):
    """Raised when a transport envelope cannot be normalized."""


@dataclass(frozen=True)
class AdoScope:
    """ADO organization and project context from an audit record."""

    org_id: str
    org_display_name: str
    project_id: str
    project_name: str


@dataclass(frozen=True)
class RepositoryRef:
    """Repository identity fields shared across lifecycle events."""

    name: str


@dataclass(frozen=True)
class NormalizedEvent:
    """Provider-neutral repository lifecycle event."""

    source: str
    event_id: str
    event_type: EventType
    scope_id: str
    repository_id: str
    occurred_at: datetime
    repository: RepositoryRef
    ado: AdoScope
    payload: dict[str, str] = field(default_factory=dict)


def strip_branch_ref(value: str) -> str:
    """Remove ADO ``refs/heads/`` prefix from a branch ref when present."""
    if value.startswith(BRANCH_REF_PREFIX):
        return value[len(BRANCH_REF_PREFIX) :]
    return value


def _parse_timestamp(value: Any) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise NormalizationError("audit Timestamp must be a non-empty ISO-8601 string")

    normalized = value.replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise NormalizationError("audit Timestamp must be a valid ISO-8601 timestamp") from exc


def _require_non_empty_str(data: dict[str, Any], key: str, *, context: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise NormalizationError(f"{context}: missing or invalid {key}")
    return value.strip()


def _require_audit_data(raw_payload: dict[str, Any]) -> dict[str, Any]:
    data = raw_payload.get("Data")
    if not isinstance(data, dict):
        raise NormalizationError("audit Data must be a JSON object")
    return data


def normalize_ado_lifecycle_event(envelope: TransportEnvelope) -> NormalizedEvent:
    """Map an ADO audit transport envelope to a normalized lifecycle event.

    Args:
        envelope: Validated transport envelope with ``source: "ado"``.

    Returns:
        Normalized lifecycle event.

    Raises:
        NormalizationError: If the audit record is unsupported or incomplete.
    """
    if envelope.source != "ado":
        raise NormalizationError('normalization requires source "ado"')

    raw = envelope.raw_payload
    action_id = _require_non_empty_str(raw, "ActionId", context="audit record")
    event_type = ADO_ACTION_TO_EVENT_TYPE.get(action_id)
    if event_type is None:
        raise NormalizationError(f"unsupported audit ActionId: {action_id}")

    event_id = _require_non_empty_str(raw, "Id", context="audit record")
    occurred_at = _parse_timestamp(raw.get("Timestamp"))

    org_id = _require_non_empty_str(raw, "ScopeId", context="audit record")
    org_display_name = _require_non_empty_str(
        raw, "ScopeDisplayName", context="audit record"
    )
    project_id = _require_non_empty_str(raw, "ProjectId", context="audit record")
    project_name = _require_non_empty_str(raw, "ProjectName", context="audit record")

    data = _require_audit_data(raw)
    repository_id = _require_non_empty_str(data, "RepoId", context="audit Data")
    repository_name = _require_non_empty_str(data, "RepoName", context="audit Data")

    payload: dict[str, str] = {}
    if event_type == "repo.created":
        default_branch = data.get("DefaultBranch")
        if isinstance(default_branch, str) and default_branch.strip():
            payload["defaultBranch"] = strip_branch_ref(default_branch.strip())
    elif event_type == "repo.renamed":
        payload["previousRepoName"] = _require_non_empty_str(
            data, "PreviousRepoName", context="audit Data"
        )
    elif event_type == "repo.default_branch_changed":
        payload["defaultBranch"] = strip_branch_ref(
            _require_non_empty_str(data, "DefaultBranch", context="audit Data")
        )
        payload["previousDefaultBranch"] = strip_branch_ref(
            _require_non_empty_str(
                data, "PreviousDefaultBranch", context="audit Data"
            )
        )

    return NormalizedEvent(
        source="ado",
        event_id=event_id,
        event_type=event_type,
        scope_id=project_id,
        repository_id=repository_id,
        occurred_at=occurred_at,
        repository=RepositoryRef(name=repository_name),
        ado=AdoScope(
            org_id=org_id,
            org_display_name=org_display_name,
            project_id=project_id,
            project_name=project_name,
        ),
        payload=payload,
    )
