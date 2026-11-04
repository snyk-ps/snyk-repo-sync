## Why

A parsed GitHub updated import copies v1 project ignores from the Azure DevOps target named by the same property value that selected the Snyk org, then leaves that target active. Operators need to deactivate or delete it after the copy, using the same order as rename, without changing deployments that have not opted in.

## What Changes

- Add `snyk.targetRemoval.onUpdate`. Allowed values are `deactivate`, `delete`, and `none`. Unset or absent means `none`.
- `none` copies or skips ignores as today and does not retire the Azure DevOps target. `deactivate` and `delete` retire that whole target only after the copy succeeds, there is nothing to copy, or `snyk.migrateIgnores` is `false`.
- Identify the target with the existing lookup: integration type `azure-repos`, in the Snyk org resolved for this event, owner equal to the extracted property value, repository name equal to the GitHub repository name, and branch equal to the import branch. That property value is the same value scope mapping used to select the org.
- A missing target skips the copy and skips retirement. The GitHub import stays complete.
- Do not deactivate or delete the previous GitHub target. Do not store a standing GitHub-to-ADO link. Clear the in-flight migration fields at the end of the attempt, including after retirement.
- The other removal keys stay `deactivate` or `delete`, default `deactivate`. An invalid `onUpdate` value fails startup.
- Update `CONFIGURATION.md`, `INGESTION.md`, and `data/config.yaml.example`.

Existing config keeps `none`, so this does not change current retirement behavior until an operator sets `onUpdate`.

## Capabilities

### New Capabilities

_None._

### Modified Capabilities

- `snyk-target-sync`: Add `onUpdate` to target removal. Only this key accepts `none`, and `none` is its default. `deactivate` and `delete` use the same whole-target removal as rename.
- `sync-worker`: A parsed GitHub updated import retires the Azure DevOps target per `onUpdate` after ignore migration. Load the new key at startup. Keep `onIgnore` in that settings requirement.
- `snyk-project-ignore-migration`: Gate Azure DevOps retirement the same way rename gates the previous target. A GitHub updated import retires the Azure DevOps target only when `onUpdate` says to.
- `sync-state`: A GitHub updated attempt still clears the five in-flight fields when the attempt finishes, and only after retirement when `onUpdate` retires the source. Those fields remain not a standing ADO link.

## Impact

- **Code:** `src/config/snyk_settings.py` gains an `onUpdate` parser that defaults to `none`. `src/worker/ignore_migration.py` retires kind `updated` with the rename-style whole-target path when the mode is `deactivate` or `delete`. `src/worker/lifecycle.py` runs that retirement after the updated copy or skip, using the id from `resolve_updated_source_target_id`.
- **APIs:** No new Snyk endpoints. `deactivate` uses the existing v1 project deactivate calls. `delete` uses `DELETE /rest/orgs/{org_id}/targets/{target_id}`. HTTP 404 means the target is already gone.
- **State:** No new repository fields. The updated snapshot still starts with an empty source target id. The follow-up resolves the Azure DevOps target again from `extractedPropertyValue` on retry.
- **Docs:** `CONFIGURATION.md` settings table, removal semantics, project-ignore section, and lifecycle table. `INGESTION.md` no longer says a GitHub updated import never deactivates an Azure DevOps target. `data/config.yaml.example` shows `onUpdate: none`.
- **Unchanged:** `repo-lifecycle`, `scope-mapping`, raw GitHub webhooks, repo delete, ignore-policy removal, code-consistent ignores, and the previous GitHub target.
