"""Normalize provider payloads into provider-neutral lifecycle events."""

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any, Literal

INVALID_NORMALIZATION_REASON = "InvalidNormalization"

EventType = Literal[
    "repo.created",
    "repo.renamed",
    "repo.deleted",
    "repo.default_branch_changed",
]

Source = Literal["ado", "github"]

ADO_ACTION_TO_EVENT_TYPE: dict[str, EventType] = {
    "Git.RepositoryCreated": "repo.created",
    "Git.RepositoryRenamed": "repo.renamed",
    "Git.RepositoryDeleted": "repo.deleted",
    "Git.RepositoryDefaultBranchChanged": "repo.default_branch_changed",
}

GITHUB_ACTIONS = frozenset({"created", "renamed", "deleted", "edited"})

BRANCH_REF_PREFIX = "refs/heads/"


class NormalizationError(ValueError):
    """Raised when an audit record cannot be normalized."""


class GitHubNoLifecycleAction(Exception):
    """Raised when a GitHub payload is valid but requires no lifecycle sync."""


class GitHubMessageShape(str, Enum):
    """Discriminator for inbound GitHub queue JSON shapes."""

    RAW_WEBHOOK = "raw_webhook"
    PARSED_CONTRACT = "parsed_contract"


@dataclass(frozen=True)
class AdoScope:
    """ADO organization and project context from an audit record."""

    org_id: str
    org_display_name: str
    project_id: str
    project_name: str


@dataclass(frozen=True)
class GitHubScope:
    """GitHub organization context from a repository webhook or parsed event."""

    org_login: str


@dataclass(frozen=True)
class RepositoryRef:
    """Repository identity fields shared across lifecycle events."""

    name: str


@dataclass(frozen=True)
class NormalizedEvent:
    """Provider-neutral repository lifecycle event."""

    source: Source
    event_id: str
    event_type: EventType
    scope_id: str
    repository_id: str
    occurred_at: datetime
    repository: RepositoryRef
    ado: AdoScope | None = None
    github: GitHubScope | None = None
    payload: dict[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.source == "ado":
            if self.ado is None or self.github is not None:
                raise ValueError("ADO events require ado scope and no github scope")
        elif self.source == "github":
            if self.github is None or self.ado is not None:
                raise ValueError("GitHub events require github scope and no ado scope")
        else:
            raise ValueError(f"unsupported source: {self.source}")


@dataclass(frozen=True)
class GitHubCanonicalInput:
    """Provider-neutral GitHub repository lifecycle fields before normalization."""

    delivery_id: str | None
    action: str
    repository_id: str
    repository_name: str
    default_branch: str | None
    updated_at: str | None
    org_login: str
    owner_type: str
    previous_repo_name: str | None = None
    previous_default_branch: str | None = None


def scope_lookup_key(event: NormalizedEvent) -> str:
    """Return the scope mapping lookup key for a normalized event."""
    if event.source == "ado":
        assert event.ado is not None
        return event.ado.project_name
    assert event.github is not None
    return event.github.org_login


def owner_name(event: NormalizedEvent) -> str:
    """Return the SCM owner name used for Snyk target owner and ignore policy."""
    return scope_lookup_key(event)


def detect_github_message_shape(payload: dict[str, Any]) -> GitHubMessageShape:
    """Classify GitHub queue JSON as raw webhook or parsed contract."""
    delivery_id = payload.get("deliveryId")
    if isinstance(delivery_id, str) and delivery_id.strip():
        return GitHubMessageShape.PARSED_CONTRACT
    return GitHubMessageShape.RAW_WEBHOOK


def normalize_github_queue_payload(
    payload: dict[str, Any],
    *,
    delivery_id: str | None = None,
) -> NormalizedEvent:
    """Normalize a GitHub queue message body (raw or parsed contract).

    Raises:
        GitHubNoLifecycleAction: When the payload is valid but needs no lifecycle sync.
        NormalizationError: When the payload is incomplete or unsupported.
    """
    shape = detect_github_message_shape(payload)
    if shape is GitHubMessageShape.PARSED_CONTRACT:
        canonical = adapt_github_parsed_contract(payload)
    else:
        canonical = adapt_github_raw_webhook(payload)
    effective_delivery = delivery_id
    if not effective_delivery and isinstance(payload.get("deliveryId"), str):
        effective_delivery = payload["deliveryId"]
    return normalize_github_repository_event(canonical, delivery_id=effective_delivery)


def adapt_github_raw_webhook(payload: dict[str, Any]) -> GitHubCanonicalInput:
    """Map raw GitHub webhook JSON to canonical GitHub lifecycle input."""
    action = _require_non_empty_str(payload, "action", context="github webhook")
    repository = _require_repository_object(payload, context="github webhook")
    owner = _require_github_owner(repository, payload, context="github webhook")
    org_login = _require_non_empty_str(owner, "login", context="github owner")
    owner_type = _require_non_empty_str(owner, "type", context="github owner")
    repository_id = _stringify_id(repository.get("id"), context="github repository.id")
    repository_name = _require_non_empty_str(repository, "name", context="github repository")
    default_branch = _optional_str(repository.get("default_branch"))
    updated_at = _optional_str(repository.get("updated_at"))
    changes = payload.get("changes")
    previous_repo_name = _nested_change_from(changes, ("repository", "name"))
    previous_default_branch = _nested_change_from(changes, ("default_branch",))
    return GitHubCanonicalInput(
        delivery_id=None,
        action=action,
        repository_id=repository_id,
        repository_name=repository_name,
        default_branch=default_branch,
        updated_at=updated_at,
        org_login=org_login,
        owner_type=owner_type,
        previous_repo_name=previous_repo_name,
        previous_default_branch=previous_default_branch,
    )


def adapt_github_parsed_contract(payload: dict[str, Any]) -> GitHubCanonicalInput:
    """Map GitHubHooks parsed contract JSON to canonical GitHub lifecycle input."""
    delivery_id = _require_non_empty_str(payload, "deliveryId", context="github parsed")
    action = _require_non_empty_str(payload, "action", context="github parsed")
    repository = _require_repository_object(payload, context="github parsed")
    owner = _require_owner_on_repository(repository, context="github parsed")
    org_login = _require_non_empty_str(owner, "login", context="github owner")
    owner_type = _require_non_empty_str(owner, "type", context="github owner")
    repository_id = _stringify_id(repository.get("id"), context="github repository.id")
    repository_name = _require_non_empty_str(repository, "name", context="github repository")
    default_branch = _optional_str(repository.get("defaultBranch"))
    updated_at = _optional_str(repository.get("updatedAt"))
    changes = payload.get("changes")
    previous_repo_name = _nested_change_from(changes, ("repository", "name"))
    previous_default_branch = _nested_change_from(changes, ("default_branch",))
    return GitHubCanonicalInput(
        delivery_id=delivery_id,
        action=action,
        repository_id=repository_id,
        repository_name=repository_name,
        default_branch=default_branch,
        updated_at=updated_at,
        org_login=org_login,
        owner_type=owner_type,
        previous_repo_name=previous_repo_name,
        previous_default_branch=previous_default_branch,
    )


def normalize_github_repository_event(
    canonical: GitHubCanonicalInput,
    *,
    delivery_id: str | None = None,
) -> NormalizedEvent:
    """Build a normalized lifecycle event from canonical GitHub input."""
    if canonical.owner_type != "Organization":
        raise GitHubNoLifecycleAction(
            f"github owner type {canonical.owner_type!r} is not Organization"
        )

    action = canonical.action.strip()
    if action not in GITHUB_ACTIONS:
        raise NormalizationError(f"unsupported github action: {action}")

    if action == "edited":
        if not canonical.previous_default_branch:
            raise GitHubNoLifecycleAction("github edited without default_branch change")
        event_type: EventType = "repo.default_branch_changed"
    elif action == "created":
        event_type = "repo.created"
    elif action == "renamed":
        event_type = "repo.renamed"
    elif action == "deleted":
        event_type = "repo.deleted"
    else:
        raise NormalizationError(f"unsupported github action: {action}")

    event_id = _resolve_github_event_id(canonical, delivery_id)
    occurred_at = _parse_github_timestamp(canonical.updated_at)

    payload: dict[str, str] = {}
    if event_type == "repo.created" and canonical.default_branch:
        payload["defaultBranch"] = strip_branch_ref(canonical.default_branch)
    if event_type == "repo.renamed" and canonical.previous_repo_name:
        payload["previousRepoName"] = canonical.previous_repo_name
    if event_type == "repo.default_branch_changed":
        if not canonical.default_branch:
            raise NormalizationError("github default branch change missing new default branch")
        payload["defaultBranch"] = strip_branch_ref(canonical.default_branch)
        assert canonical.previous_default_branch is not None
        payload["previousDefaultBranch"] = strip_branch_ref(canonical.previous_default_branch)

    scope_id = canonical.org_login
    return NormalizedEvent(
        source="github",
        event_id=event_id,
        event_type=event_type,
        scope_id=scope_id,
        repository_id=canonical.repository_id,
        occurred_at=occurred_at,
        repository=RepositoryRef(name=canonical.repository_name),
        github=GitHubScope(org_login=scope_id),
        payload=payload,
    )


def strip_branch_ref(value: str) -> str:
    """Remove ADO ``refs/heads/`` prefix from a branch ref when present."""
    if value.startswith(BRANCH_REF_PREFIX):
        return value[len(BRANCH_REF_PREFIX) :]
    return value


def _resolve_github_event_id(
    canonical: GitHubCanonicalInput,
    delivery_id: str | None,
) -> str:
    for candidate in (delivery_id, canonical.delivery_id):
        if isinstance(candidate, str) and candidate.strip():
            return candidate.strip()
    if canonical.updated_at:
        return (
            f"github:{canonical.repository_id}:{canonical.action}:{canonical.updated_at}"
        )
    raise NormalizationError("github event requires deliveryId or repository.updated_at")


def _parse_github_timestamp(value: str | None) -> datetime:
    if not value or not value.strip():
        return datetime.now(tz=UTC)
    return _parse_timestamp(value)


def _parse_timestamp(value: Any) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise NormalizationError("timestamp must be a non-empty ISO-8601 string")

    normalized = value.replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise NormalizationError("timestamp must be a valid ISO-8601 timestamp") from exc


def _require_non_empty_str(data: dict[str, Any], key: str, *, context: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise NormalizationError(f"{context}: missing or invalid {key}")
    return value.strip()


def _optional_str(value: Any) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _stringify_id(value: Any, *, context: str) -> str:
    if isinstance(value, int):
        return str(value)
    if isinstance(value, str) and value.strip():
        return value.strip()
    raise NormalizationError(f"{context}: missing or invalid id")


def _require_repository_object(payload: dict[str, Any], *, context: str) -> dict[str, Any]:
    repository = payload.get("repository")
    if not isinstance(repository, dict):
        raise NormalizationError(f"{context}: missing repository object")
    return repository


def _require_owner_on_repository(repository: dict[str, Any], *, context: str) -> dict[str, Any]:
    owner = repository.get("owner")
    if not isinstance(owner, dict):
        raise NormalizationError(f"{context}: missing repository.owner object")
    return owner


def _require_github_owner(
    repository: dict[str, Any],
    payload: dict[str, Any],
    *,
    context: str,
) -> dict[str, Any]:
    owner = repository.get("owner")
    if isinstance(owner, dict):
        return owner
    organization = payload.get("organization")
    if isinstance(organization, dict):
        login = organization.get("login")
        if isinstance(login, str) and login.strip():
            return {"login": login.strip(), "type": "Organization"}
    raise NormalizationError(f"{context}: missing repository.owner object")


def _nested_change_from(changes: Any, path: tuple[str, ...]) -> str | None:
    if not isinstance(changes, dict):
        return None
    node: Any = changes
    for key in path:
        if not isinstance(node, dict):
            return None
        node = node.get(key)
    if not isinstance(node, dict):
        return None
    value = node.get("from")
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _require_audit_data(audit_record: dict[str, Any]) -> dict[str, Any]:
    data = audit_record.get("Data")
    if not isinstance(data, dict):
        raise NormalizationError("audit Data must be a JSON object")
    return data


def normalize_ado_audit_record(audit_record: dict[str, Any]) -> NormalizedEvent:
    """Map an ADO audit record to a normalized lifecycle event.

    Args:
        audit_record: Audit object from Event Grid ``data``.

    Returns:
        Normalized lifecycle event.

    Raises:
        NormalizationError: If the audit record is unsupported or incomplete.
    """
    raw = audit_record
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
        previous_default_branch = data.get("PreviousDefaultBranch")
        if isinstance(previous_default_branch, str) and previous_default_branch.strip():
            payload["previousDefaultBranch"] = strip_branch_ref(
                previous_default_branch.strip()
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
