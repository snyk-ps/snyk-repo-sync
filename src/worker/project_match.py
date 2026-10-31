"""Match source Snyk projects to destination projects for ignore migration."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence

from snyk.client import SnykProject


class ProjectMatchError(Exception):
    """Raised when a source project with ignores has no unique destination."""


def match_projects(
    sources: Sequence[SnykProject],
    destinations: Sequence[SnykProject],
    *,
    import_branch: str,
    source_ids_with_ignores: set[str],
) -> dict[str, str]:
    """Return source project id to destination project id for eligible projects.

    Deactivated projects are ignored. A source project with no ignores does not
    need a destination. A source project with ignores and no unique match fails.

    Args:
        sources: Projects to copy from.
        destinations: Projects to copy onto.
        import_branch: Destination branch used to break same-file source ties.
        source_ids_with_ignores: Source project ids that have at least one ignore.

    Returns:
        Mapping of source project id to destination project id.

    Raises:
        ProjectMatchError: When a source project with ignores is not unique.
    """
    eligible_sources = [project for project in sources if not project.deactivated]
    eligible_destinations = [project for project in destinations if not project.deactivated]
    matches: dict[str, str] = {}
    consumed_source_ids: set[str] = set()
    consumed_destination_ids: set[str] = set()

    _match_unique_empty_files(
        eligible_sources,
        eligible_destinations,
        matches=matches,
        consumed_source_ids=consumed_source_ids,
        consumed_destination_ids=consumed_destination_ids,
    )
    remaining_sources = [
        project for project in eligible_sources if project.id not in consumed_source_ids
    ]
    remaining_destinations = [
        project for project in eligible_destinations if project.id not in consumed_destination_ids
    ]
    grouped: dict[tuple[str, str], list[SnykProject]] = defaultdict(list)
    for project in remaining_sources:
        grouped[(project.project_type, project.target_file)].append(project)

    for group in grouped.values():
        selected = _select_source(
            group,
            import_branch=import_branch,
            source_ids_with_ignores=source_ids_with_ignores,
        )
        if selected is None:
            continue
        dest_matches = [
            project
            for project in remaining_destinations
            if project.project_type == selected.project_type
            and project.target_file == selected.target_file
        ]
        if len(dest_matches) == 1:
            matches[selected.id] = dest_matches[0].id
            continue
        if selected.id in source_ids_with_ignores:
            raise ProjectMatchError(
                f"source project {selected.id} has ignores and no unique destination"
            )
    return matches


def _match_unique_empty_files(
    sources: Sequence[SnykProject],
    destinations: Sequence[SnykProject],
    *,
    matches: dict[str, str],
    consumed_source_ids: set[str],
    consumed_destination_ids: set[str],
) -> None:
    sources_by_type: dict[str, list[SnykProject]] = defaultdict(list)
    destinations_by_type: dict[str, list[SnykProject]] = defaultdict(list)
    for project in sources:
        if not project.target_file:
            sources_by_type[project.project_type].append(project)
    for project in destinations:
        if not project.target_file:
            destinations_by_type[project.project_type].append(project)
    for project_type, typed_sources in sources_by_type.items():
        typed_destinations = destinations_by_type.get(project_type, [])
        if len(typed_sources) != 1 or len(typed_destinations) != 1:
            continue
        source = typed_sources[0]
        destination = typed_destinations[0]
        matches[source.id] = destination.id
        consumed_source_ids.add(source.id)
        consumed_destination_ids.add(destination.id)


def _select_source(
    group: Sequence[SnykProject],
    *,
    import_branch: str,
    source_ids_with_ignores: set[str],
) -> SnykProject | None:
    if len(group) == 1:
        return group[0]
    branch = import_branch.strip()
    if branch:
        branch_matches = [project for project in group if project.target_reference == branch]
    else:
        branch_matches = []
    if len(branch_matches) == 1:
        return branch_matches[0]
    tied = branch_matches if len(branch_matches) > 1 else list(group)
    if any(project.id in source_ids_with_ignores for project in tied):
        raise ProjectMatchError("source projects with ignores have no unique match")
    return None
