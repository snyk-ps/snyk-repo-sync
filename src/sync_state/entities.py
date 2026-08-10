"""Sync-state entity models for Azure Table Storage rows."""

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Literal

ImportStatus = Literal["pending", "failed", "complete"]
RepositoryStatus = Literal["pending", "active", "inactive"]


@dataclass(frozen=True)
class RepositoryState:
    """Per-repository sync state stored under a repository id row key."""

    repo_name: str
    snyk_target_id: str
    default_branch: str
    status: RepositoryStatus
    desired_state_hash: str
    last_event_id: str
    tag_applied: bool
    import_job_id: str
    import_status: ImportStatus

    @classmethod
    def from_entity(cls, entity: Mapping[str, Any]) -> "RepositoryState":
        """Build repository state from a Table Storage entity."""
        return cls(
            repo_name=str(entity.get("repoName", "")),
            snyk_target_id=str(entity.get("snykTargetId", "")),
            default_branch=str(entity.get("defaultBranch", "")),
            status=_parse_repository_status(entity.get("status")),
            desired_state_hash=str(entity.get("desiredStateHash", "")),
            last_event_id=str(entity.get("lastEventId", "")),
            tag_applied=bool(entity.get("tagApplied", False)),
            import_job_id=str(entity.get("importJobId", "")),
            import_status=_parse_import_status(entity.get("importStatus")),
        )

    def to_entity(self, partition_key: str, repository_id: str) -> dict[str, Any]:
        """Serialize repository state to a Table Storage entity."""
        return {
            "PartitionKey": partition_key,
            "RowKey": repository_id,
            "repoName": self.repo_name,
            "snykTargetId": self.snyk_target_id,
            "defaultBranch": self.default_branch,
            "status": self.status,
            "desiredStateHash": self.desired_state_hash,
            "lastEventId": self.last_event_id,
            "tagApplied": self.tag_applied,
            "importJobId": self.import_job_id,
            "importStatus": self.import_status,
        }


def repository_partition_key(source: str, scope_id: str) -> str:
    """Build the repository row partition key."""
    return f"{source}:{scope_id}"


def _parse_import_status(value: Any) -> ImportStatus:
    if value in {"pending", "failed", "complete"}:
        return value
    return "pending"


def _parse_repository_status(value: Any) -> RepositoryStatus:
    if value in {"pending", "active", "inactive"}:
        return value
    if value == "synced":
        return "active"
    return "pending"
