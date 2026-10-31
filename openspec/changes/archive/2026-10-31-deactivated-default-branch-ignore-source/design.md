## Context

Default-branch ignore migration runs after the new branch import completes. On a GitHub Enterprise target, that import deactivates the previous branch's projects before the `ignore_migration` follow-up lists them. `GET /v1/org/{orgId}/project/{projectId}/ignores` still returns the ignores for those projects.

The current copy treats a deactivated project as ineligible in three places: the branch filter drops it, the copy loop never calls the ignores API, and project matching drops it again. The follow-up then logs `outcome=skipped` and retires the previous branch. Rename and parsed GitHub updated imports do not deactivate their copy source before the read.

## Goals / Non-Goals

**Goals:**

- Read v1 project ignores from the previous `target_reference` after a default-branch import, including projects that are already deactivated.
- Match those source projects to active projects on the new branch.
- Leave rename and parsed GitHub updated source selection limited to projects that are not deactivated.
- Keep destination projects limited to projects that are not deactivated.

**Non-Goals:**

- Caching ignore documents in the queue message or in sync state.
- Reading ignores before the import starts.
- Copying ignores onto a deactivated destination project.
- Changing retirement order, removal mode, or the v1 ignore create body.
- Treating a deactivated rename source or a deactivated Azure DevOps source as eligible.

## Decisions

### 1. Read the deactivated previous branch after import

The default-branch source list includes projects whose `target_reference` is the previous branch, whether or not they are deactivated. The copy calls the v1 ignores API for each of those projects. The destination list stays limited to projects that are not deactivated and whose `target_reference` is the new branch.

Alternative considered: read ignores before import and store them on the follow-up message. Rejected because the ignores API still answers after deactivation, and the queue message would carry ignore text.

### 2. Matching keeps deactivated sources only when the caller passes them

Project matching does not drop a source project for being deactivated. It still drops a deactivated destination. Rename and parsed GitHub updated callers continue to pass only active source projects, so their copy behavior stays the same. A default-branch caller passes the previous-branch projects, including deactivated ones.

A deactivated previous-branch project with ignores and no unique active destination still fails the migration and does not retire the source.

### 3. Retirement is unchanged

`deactivate` still skips a previous-branch project that is already deactivated. `delete` still deletes those projects. The target stays.

## Risks / Trade-offs

- [A project the operator deactivated on the previous branch before the branch change is also read] → The worker cannot tell that project from one Snyk deactivated during import. Both are previous-branch projects, and both are copied when they still have ignores.
- [Rename or updated callers forget to filter deactivated sources] → Those callers keep the active-only filter. Tests cover a deactivated rename source producing no ignores request.
- [The new branch has no active project for a source that has ignores] → The existing unmatched-source failure applies. The previous branch is not retired while the copy is pending.

## Migration Plan

Deploy the worker. Default-branch events processed before this release, whose previous-branch projects were already retired, cannot recover ignores. Rollback restores the active-only source filter; new default-branch events then skip the copy again when Snyk has already deactivated the previous branch.

## Open Questions

None.
