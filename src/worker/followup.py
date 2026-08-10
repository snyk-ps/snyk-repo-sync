"""Internal follow-up queue message schema and retry helpers."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal

SyncPhase = Literal["import_poll", "lifecycle_deferred"]
ImportStatusValue = Literal["pending", "failed"]

IMPORT_POLL_PHASE: SyncPhase = "import_poll"
LIFECYCLE_DEFERRED_PHASE: SyncPhase = "lifecycle_deferred"
IMPORT_JOB_FAILED_REASON = "ImportJobFailed"
MAX_IMPORT_POLL_RETRIES = 5
IMPORT_POLL_BASE_SECONDS = 30
IMPORT_POLL_MAX_SECONDS = 900


@dataclass(frozen=True)
class ScheduledFollowUp:
    """Follow-up message to schedule on the same Service Bus queue."""

    body: dict[str, Any]
    delay_seconds: int


@dataclass(frozen=True)
class InternalFollowUpMessage:
    """Parsed internal worker follow-up envelope."""

    sync_phase: SyncPhase
    source: str
    scope_id: str
    repository_id: str
    source_event_id: str
    retry_count: int
    import_job_id: str | None = None
    import_status: ImportStatusValue | None = None
    event_type: str | None = None
    repository_name: str | None = None
    ado_project_name: str | None = None
    default_branch: str | None = None
    payload: dict[str, str] | None = None


def compute_backoff_seconds(
    retry_count: int,
    *,
    base_seconds: int = IMPORT_POLL_BASE_SECONDS,
    max_seconds: int = IMPORT_POLL_MAX_SECONDS,
) -> int:
    """Return exponential backoff delay capped at ``max_seconds``."""
    return min(base_seconds * (2**retry_count), max_seconds)


def build_import_poll_message(
    *,
    source: str,
    scope_id: str,
    repository_id: str,
    source_event_id: str,
    import_job_id: str,
    import_status: ImportStatusValue,
    retry_count: int,
    ado_project_name: str,
) -> dict[str, Any]:
    """Build an ``import_poll`` follow-up envelope."""
    return {
        "syncPhase": IMPORT_POLL_PHASE,
        "source": source,
        "scopeId": scope_id,
        "repositoryId": repository_id,
        "sourceEventId": source_event_id,
        "importJobId": import_job_id,
        "importStatus": import_status,
        "retryCount": retry_count,
        "adoProjectName": ado_project_name,
        "occurredAt": datetime.now(tz=UTC).isoformat(),
    }


def build_lifecycle_deferred_message(
    *,
    source: str,
    scope_id: str,
    repository_id: str,
    source_event_id: str,
    event_type: str,
    repository_name: str,
    ado_project_name: str,
    default_branch: str,
    payload: dict[str, str],
    retry_count: int,
) -> dict[str, Any]:
    """Build a ``lifecycle_deferred`` follow-up envelope."""
    return {
        "syncPhase": LIFECYCLE_DEFERRED_PHASE,
        "source": source,
        "scopeId": scope_id,
        "repositoryId": repository_id,
        "sourceEventId": source_event_id,
        "eventType": event_type,
        "repositoryName": repository_name,
        "adoProjectName": ado_project_name,
        "defaultBranch": default_branch,
        "payload": payload,
        "retryCount": retry_count,
        "occurredAt": datetime.now(tz=UTC).isoformat(),
    }


def parse_internal_follow_up(data: dict[str, Any]) -> InternalFollowUpMessage:
    """Parse a validated internal follow-up envelope."""
    sync_phase = data.get("syncPhase")
    if sync_phase not in {IMPORT_POLL_PHASE, LIFECYCLE_DEFERRED_PHASE}:
        raise ValueError("unsupported syncPhase")

    source = _require_str(data, "source")
    scope_id = _require_str(data, "scopeId")
    repository_id = _require_str(data, "repositoryId")
    source_event_id = _require_str(data, "sourceEventId")
    retry_count = data.get("retryCount", 0)
    if isinstance(retry_count, bool) or not isinstance(retry_count, int) or retry_count < 0:
        raise ValueError("retryCount must be a non-negative integer")

    import_job_id = data.get("importJobId")
    if import_job_id is not None and (not isinstance(import_job_id, str) or not import_job_id.strip()):
        raise ValueError("importJobId must be a non-empty string when present")
    import_status = data.get("importStatus")
    if import_status is not None and import_status not in {"pending", "failed"}:
        raise ValueError("importStatus must be pending or failed when present")

    event_type = data.get("eventType")
    repository_name = data.get("repositoryName")
    ado_project_name = data.get("adoProjectName")
    if ado_project_name is not None and (
        not isinstance(ado_project_name, str) or not ado_project_name.strip()
    ):
        raise ValueError("adoProjectName must be a non-empty string when present")
    default_branch = data.get("defaultBranch")
    payload_raw = data.get("payload")
    payload: dict[str, str] | None = None
    if payload_raw is not None:
        if not isinstance(payload_raw, dict):
            raise ValueError("payload must be a mapping when present")
        payload = {str(key): str(value) for key, value in payload_raw.items()}

    return InternalFollowUpMessage(
        sync_phase=sync_phase,  # type: ignore[arg-type]
        source=source,
        scope_id=scope_id,
        repository_id=repository_id,
        source_event_id=source_event_id,
        retry_count=retry_count,
        import_job_id=import_job_id.strip() if isinstance(import_job_id, str) else None,
        import_status=import_status,  # type: ignore[arg-type]
        event_type=event_type.strip() if isinstance(event_type, str) else None,
        repository_name=repository_name.strip() if isinstance(repository_name, str) else None,
        ado_project_name=ado_project_name.strip() if isinstance(ado_project_name, str) else None,
        default_branch=default_branch.strip() if isinstance(default_branch, str) else None,
        payload=payload,
    )


def _require_str(data: dict[str, Any], key: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{key} must be a non-empty string")
    return value.strip()
