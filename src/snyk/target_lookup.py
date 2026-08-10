"""Helpers for matching Snyk REST target records to ADO repositories."""

from __future__ import annotations

from typing import Any


def normalize_repo_name(repo_name: str) -> str:
    """Return repository name without a trailing ``.git`` suffix."""
    name = repo_name.strip()
    if name.lower().endswith(".git"):
        return name[:-4]
    return name


def parse_target_records(payload: Any) -> list[dict[str, Any]]:
    """Extract target records from a Snyk REST targets list response."""
    if not isinstance(payload, dict):
        return []
    data = payload.get("data")
    if not isinstance(data, list):
        return []
    records: list[dict[str, Any]] = []
    for item in data:
        if isinstance(item, dict):
            records.append(item)
    return records


def extract_next_link(payload: Any) -> str | None:
    """Return the pagination next link from a Snyk REST JSON:API payload."""
    if not isinstance(payload, dict):
        return None
    links = payload.get("links")
    if not isinstance(links, dict):
        return None
    next_link = links.get("next")
    if isinstance(next_link, str) and next_link.strip():
        return next_link.strip()
    return None


def select_target_id(
    records: list[dict[str, Any]],
    *,
    owner: str,
    repo_name: str,
    branch: str = "",
) -> str | None:
    """Return the best matching Snyk target id for an ADO repository."""
    normalized_repo = normalize_repo_name(repo_name).lower()
    normalized_owner = owner.strip().lower()
    normalized_branch = branch.strip().lower()

    candidates: list[tuple[int, str]] = []
    for record in records:
        target_id = record.get("id")
        if not isinstance(target_id, str) or not target_id.strip():
            continue
        attributes = record.get("attributes")
        if not isinstance(attributes, dict):
            continue
        display_name = attributes.get("display_name")
        if not isinstance(display_name, str):
            continue
        display_lower = display_name.lower()
        repo_token = normalized_repo
        if repo_token not in display_lower and f"{repo_token}.git" not in display_lower:
            continue

        score = 10
        if normalized_owner:
            owner_prefix = f"{normalized_owner}/"
            if display_lower.startswith(owner_prefix):
                score += 20
            elif normalized_owner in display_lower:
                score += 5

        if normalized_branch:
            branch_markers = (
                f"({normalized_branch})",
                f"/{normalized_branch}",
                f":{normalized_branch}",
            )
            if any(marker in display_lower for marker in branch_markers):
                score += 30
            else:
                score -= 5

        candidates.append((score, target_id.strip()))

    if not candidates:
        return None

    candidates.sort(key=lambda item: item[0], reverse=True)
    best_score = candidates[0][0]
    best_ids = {target_id for score, target_id in candidates if score == best_score}
    if len(best_ids) == 1:
        return next(iter(best_ids))
    return candidates[0][1]


def parse_project_ids(payload: Any) -> list[str]:
    """Extract project ids from a Snyk REST projects list response."""
    if not isinstance(payload, dict):
        return []
    data = payload.get("data")
    if not isinstance(data, list):
        return []
    project_ids: list[str] = []
    for item in data:
        if isinstance(item, dict):
            project_id = item.get("id")
            if isinstance(project_id, str) and project_id.strip():
                project_ids.append(project_id.strip())
    return project_ids
