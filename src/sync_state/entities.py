"""Sync-state entity models for Azure Table Storage rows."""

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class RepositoryState:
    """Per-repository sync state stored under a repository id row key."""

    repo_name: str
    snyk_target_id: str
    default_branch: str
    status: str
    desired_state_hash: str
    last_event_id: str
    tag_applied: bool

    @classmethod
    def from_entity(cls, entity: Mapping[str, Any]) -> "RepositoryState":
        """Build repository state from a Table Storage entity."""
        return cls(
            repo_name=str(entity["repoName"]),
            snyk_target_id=str(entity["snykTargetId"]),
            default_branch=str(entity["defaultBranch"]),
            status=str(entity["status"]),
            desired_state_hash=str(entity["desiredStateHash"]),
            last_event_id=str(entity["lastEventId"]),
            tag_applied=bool(entity["tagApplied"]),
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
        }
