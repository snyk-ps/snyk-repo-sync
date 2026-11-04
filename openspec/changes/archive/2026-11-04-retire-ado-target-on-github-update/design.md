## Context

A parsed GitHub updated body normalizes to `repo.created` and imports a GitHub target. After that import, follow-up phase `ignore_migration` with kind `updated` copies v1 project ignores from an `azure-repos` target and then stops. `retire_migration_source` returns immediately unless the kind is `rename` or `default_branch`.

The Azure DevOps target is not snapshotted before import. The follow-up resolves it with `resolve_updated_source_target_id`: the Snyk org resolved for the event, owner equal to `extractedPropertyValue`, repository name equal to the GitHub repository name, branch equal to the import branch, and source type `azure-repos`. That property value is the same value scope mapping used as the candidate for the Snyk org. The updated snapshot stores kind `updated` and empty source ids. Those fields are cleared at the end of the attempt and are not a standing ADO link.

The other removal keys accept only `deactivate` or `delete` and default to `deactivate`. Their parser treats a missing value as `deactivate`.

## Goals / Non-Goals

**Goals:**

- Add `snyk.targetRemoval.onUpdate` with `deactivate`, `delete`, and `none`. Absent means `none`.
- When `onUpdate` is `deactivate` or `delete`, retire the resolved Azure DevOps target only after the ignore copy succeeds, there is nothing to copy, or `snyk.migrateIgnores` is `false`.
- When `onUpdate` is `none`, keep today's outcome: copy or skip, and leave the Azure DevOps target in place.
- Use the same whole-target removal as rename. Retry a failed copy or a failed retirement without starting another import.
- Document the setting and the new order.

**Non-Goals:**

- A new capability.
- Retiring the previous GitHub target.
- A standing GitHub-to-ADO link, or writing the resolved Azure DevOps target id onto the GitHub row after the attempt.
- Changing `onRename`, `onDefaultBranchChange`, `onRepoDelete`, or `onIgnore`.
- Raw GitHub webhook create, edit, rename, or delete behavior.
- Code-consistent ignores and project tagging.

## Decisions

### 1. `none` is the default, and it has its own parser

`onUpdate` accepts `deactivate`, `delete`, and `none`. A missing key or a missing `targetRemoval` section means `none`. Any other value fails startup. The existing parser still defaults the other four keys to `deactivate` and still rejects `none` for those keys.

`none` was chosen over `skip` and `retain`. `skip` already means the ignore copy did not run. `none` says the target is not retired.

Alternative considered: default `onUpdate` to `deactivate`, matching the other keys. Rejected because existing deployments would start retiring Azure DevOps targets on the next updated import.

### 2. Retire the whole Azure DevOps target after the copy

The `ignore_migration` follow-up for kind `updated` keeps its current copy. After the copy returns `succeeded` or `skipped`, and only when `onUpdate` is `deactivate` or `delete`, the worker retires the same target id the copy used.

`deactivate` deactivates every project on that target through the v1 Projects API. `delete` deletes the target with `DELETE /rest/orgs/{org_id}/targets/{target_id}`. HTTP 404 means the target is already gone. This matches rename, not default-branch project removal. The GitHub import replaces the Azure DevOps target for that repository.

A missing lookup skips the copy and skips retirement. The GitHub import stays complete. `migrateIgnores: false`, and a target whose eligible projects have no ignores, are successful skips and still retire when `onUpdate` asks for retirement.

A copy failure reschedules `ignore_migration` and does not retire. A retirement failure reschedules the same follow-up and does not start another import. The retry budget and dead-letter reason `IgnoreMigrationFailed` stay as they are. The source stays active until retirement succeeds.

Alternative considered: retire before the copy. Rejected because the ignores live on the Azure DevOps projects.

### 3. Resolve the target again from the message

Retirement uses `resolve_updated_source_target_id` during the follow-up. The org is the resolved Snyk org stored for the GitHub import. The owner is `extractedPropertyValue` already carried on the follow-up. The repository name and branch come from the GitHub repository row.

The worker does not write that Azure DevOps target id into `ignoreSourceTargetId` as a lasting link. A retirement retry resolves the target again from the property value. `deactivate` skips projects that are already deactivated. `delete` treats HTTP 404 as already gone.

When no property value was extracted, the lookup has no owner and there is no target to retire.

Alternative considered: snapshot the Azure DevOps target id before import, as rename does. Rejected because the GitHub import does not overwrite an Azure DevOps target id, and the current contract forbids a standing link.

### 4. The previous GitHub target stays

`onUpdate` applies only to the `azure-repos` target found by that lookup. The GitHub target created by the import, and any previous GitHub target left behind by an org move, stay active.

## Risks / Trade-offs

- [Risk] `delete` cannot be undone. → The default is `none`. Docs state that `delete` removes the Azure DevOps target.
- [Risk] The lookup could select a different Azure DevOps target than the one an operator expects. → Retirement uses the same org, owner, repository name, and branch as the ignore copy, so the copy and the retirement stay on one target.
- [Risk] A retry after a partial deactivate could run the copy again. → The copy already leaves an ignore in place when the destination has that issue id and path. Retirement then continues.
- [Risk] Scope resolution can land in a default or stored org when the property value did not match a static row. → The target is still sought in the org resolved for this event, with the extracted property value as the owner. No property value means no retirement.

## Migration Plan

Deploy the worker before setting `onUpdate`. Absent config stays `none`, so current imports keep the Azure DevOps target. Operators set `deactivate` or `delete` when they want retirement. Rollback is to set the key back to `none` or remove it. Targets already deleted are not restored.

## Open Questions

None. `none` is the do-nothing value.
