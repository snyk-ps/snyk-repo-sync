## Context

Rename and default-branch change currently resolve the old Snyk target, deactivate every project on it or delete the target, and only then import. v1 project ignores live on those projects, so the copy source is gone before the new projects exist. Canonical specs require that outcome.

A Snyk target is one repository on one integration. A default-branch change does not create a second target. Importing the new branch adds projects whose `target_reference` is the new branch beside projects whose `target_reference` is the old branch. Today's removal lists every project for the target id, or deletes the target, so it cannot run after that import.

The parsed GitHub updated body normalizes to `repo.created`. It imports a GitHub target and must leave any Azure DevOps target in place. The extracted `azure-devops-project` value is the ADO project name used as the owner segment of that ADO target.

## Goals / Non-Goals

**Goals:**

- After a new import is complete, copy v1 project ignores onto the matching new projects when `snyk.migrateIgnores` is true, then retire the source where this change already retires it.
- On default branch change, retire only the previous branch's projects.
- On GitHub updated, copy from the ADO target named by `azure-devops-project` when it exists, and re-import when the stored org or integration differs.
- Retry a failed copy without retiring the source. Document the operator-visible behavior.

**Non-Goals:**

- Code consistent ignores.
- Deactivating or deleting the ADO target, or the previous GitHub target, after an updated import.
- A standing GitHub-to-ADO link, or finding and inactivating the ADO sync-state row.
- Project tagging.

## Decisions

### 1. Copy after import, retire after copy

Rename and default-branch change snapshot the source before import overwrites `snykTargetId` and `defaultBranch`. The import job still completes as it does today. A follow-up then copies ignores and, for those two events, retires the source.

Retirement failure retries retirement and does not start another import. Copy failure retries the copy and does not retire the source.

Alternative considered: keep remove-then-import and cache ignores in the queue message. Rejected because the payload can be large, the cache can go stale, and a default-branch delete would destroy the target the new branch must attach to.

### 2. Source and retirement differ by event

| Event | Copy source | Retirement after a successful copy or a skip |
| --- | --- | --- |
| Rename | Previous target for this repository (stored id, else lookup by previous name) | Whole target, per `onRename`. `delete` still deletes the target. |
| Default branch change | Projects on the current target whose `target_reference` is the previous branch | Only those projects, per `onDefaultBranchChange`. `deactivate` calls v1 project deactivate. `delete` calls `DELETE /rest/orgs/{org_id}/projects/{project_id}`. The target stays. |
| GitHub updated | `azure-repos` target in the resolved Snyk org whose owner is the extracted `azure-devops-project` value, whose repository name is the GitHub repository name, and whose branch is the import branch | None. |
| Delete, ignore-policy match | None | Unchanged whole-target removal. No copy. |

A missing source, or a source with no ignores, is a successful skip. Retirement for rename and default branch change still runs.

Updated uses the current extracted property (`newPropertyValues`). The normalized event records that the body was a parsed updated import so a plain `repo.created` does not look up an ADO target.

When several ADO projects share a type and target file, the copy prefers the project whose `target_reference` equals the GitHub import branch. A remaining tie fails the copy.

### 3. Org change re-imports only the updated body

When the repository row already has a non-empty `snykOrgId` or `snykIntegrationType` and the resolution for a parsed updated body differs, desired state is not current. The worker imports into the resolved org. A blank stored org is a backfill, not a move. The previous GitHub target stays active in Snyk. Sync state then points at the new target only.

### 4. v1 project ignores, matched by type and target file

Read `GET /v1/org/{orgId}/project/{projectId}/ignores`. Write each missing ignore with `POST /v1/org/{orgId}/project/{projectId}/ignore/{issueId}`.

Copy issue id, ignore path, reason, reason type, `disregardIfFixable`, and expiry. Do not send `ignoredBy` or `created`. The token user owns the new ignore.

Read the destination project first and skip an issue id plus path already present, so a retry does not add a second copy.

Projects match on `type` plus `target_file`. A project with an empty `target_file` matches on `type` only when exactly one source project and one destination project have that type and an empty file. A source project with ignores and no unique match fails the copy. A source project with no ignores does not need a match.

Only projects that are not deactivated are eligible.

### 5. In-flight state and one follow-up phase

Before import overwrites the row, persist:

- `ignoreMigrationKind`: `rename`, `default_branch`, or `updated`
- `ignoreMigrationStatus`: `pending`
- `ignoreSourceOrgId`, `ignoreSourceTargetId`, and `ignoreSourceTargetReference` when already known

`import_poll` still means the import job. When the job succeeds and a kind is set, it schedules `syncPhase: ignore_migration` and completes. That phase resolves a missing ADO source, copies when `snyk.migrateIgnores` is true, retires when required, then clears the in-flight fields. Failures reschedule it with the existing retry budget (5) and dead-letter reason `IgnoreMigrationFailed`.

Clearing waits until retirement finishes when this event retires the source. Updated clears after the copy or skip.

### 6. `snyk.migrateIgnores` defaults to true

Operator config key `snyk.migrateIgnores` is a boolean. Absent `snyk` section or absent key means `true`. `true` runs the copy. `false` is a successful skip: the worker does not call the v1 ignore APIs, and rename and default-branch retirement still run after import. A non-boolean value fails startup, same as an invalid removal mode.

Alternative considered: default `false` so existing deployments keep today's drop-ignores behavior until opted in. Rejected because the reason for this change is to stop dropping ignores, and operators who need the old behavior can set `false`.

### 7. Documentation

`CONFIGURATION.md` gains the new order in the lifecycle table, the default-branch project scope, the updated ADO copy, the v1-only boundary, the in-flight state fields, and `snyk.migrateIgnores`. `data/config.yaml.example` shows `migrateIgnores: true`.

## Risks / Trade-offs

- [Rename leaves two targets active until the copy finishes] → Retirement is the step immediately after a successful copy or skip. A failed copy leaves the old target active on purpose.
- [Default-branch `delete` used to delete the target] → It now deletes the previous branch's projects. Operators who expected the target id to disappear need the doc change in the same release.
- [GitHub repository name differs from the ADO repository name] → ADO lookup misses, the copy is skipped, and the GitHub import still completes. The log says the ADO target was not found.
- [Updated org move drops the previous GitHub target id from sync state] → That target stays active in Snyk with no row pointing at it. Retiring it is out of scope.
- [Ambiguous project match blocks rename and branch retirement] → The old projects stay until an operator resolves the overlap or the message dead-letters. Ignores are not discarded.
- [New ignores are owned by `SNYK_TOKEN`] → Document that. The original `ignoredBy` user is not preserved.

## Migration Plan

Deploy the worker. Events already removed before this release cannot recover ignores. In-flight imports that snapshotted nothing follow the new tail only when the row has `ignoreMigrationKind` set; older pending rows finish import without a copy.

Rollback to the previous worker restores remove-before-import for new events. Rows left in `ignore_migration` retry on the new code and are a no-op or a failed poll on the old code; drain or poison those follow-ups before rollback.

## Open Questions

None. ADO-target deactivation after updated is a separate change.
