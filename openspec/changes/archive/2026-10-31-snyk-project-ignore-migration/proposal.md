## Why

Re-importing a repository drops v1 project ignores, because those ignores live on the Snyk project and the current rename and default-branch flows retire the old projects before the new ones exist. Operators need the ignores copied onto the new projects first, and a GitHub updated import needs the same copy from the related Azure DevOps target.

## What Changes

- Add a v1 project-ignore migration capability. After the new target is imported, copy project ignores from the source projects onto the matching destination projects, then retire the source where this change already retires it.
- Add `snyk.migrateIgnores` (boolean, default `true`). When `true`, the worker copies v1 project ignores. When `false`, it skips the copy and does not call the v1 ignore APIs. Rename and default-branch retirement still run. A non-boolean value fails startup.
- **BREAKING:** On rename, import the new repository name before removing the previous target. Removal still follows `snyk.targetRemoval.onRename` and runs only after the copy succeeds, there is nothing to copy, or `snyk.migrateIgnores` is `false`.
- **BREAKING:** On default branch change, the old and new branches are `target_reference` values on one Snyk target. Import the new branch, copy ignores from the old branch's projects to the new branch's projects when `snyk.migrateIgnores` is `true`, then deactivate or delete only the old branch's projects. The target stays.
- On GitHub updated, import the GitHub repository, including when the resolved Snyk org or integration differs from the non-empty values already stored. When `snyk.migrateIgnores` is `true`, copy ignores from the Azure DevOps target identified by the extracted `azure-devops-project` value when that target exists. Leave the ADO target and any previous GitHub target active.
- Document the operator-visible behavior in `CONFIGURATION.md`.
- Repo delete and ignore-policy matches do not copy ignores. They still remove the existing target as they do today.
- Code consistent ignores are unchanged. This change does not call those APIs.
- Deactivating or deleting the ADO target after a GitHub updated import is a follow-up change. This change does not store a standing GitHub-to-ADO link.

## Capabilities

### New Capabilities

- `snyk-project-ignore-migration`: Copy v1 project ignores after import when `snyk.migrateIgnores` is true, match projects, retry failed copies, and gate source retirement on a successful copy or a configured skip.

### Modified Capabilities

- `snyk-target-sync`: Replace "issue ignores are not migrated" and the remove-before-reimport order. Default-branch removal applies to the previous branch's projects, not the whole target.
- `repo-lifecycle`: Rename and default-branch handlers import first, copy ignores, then retire the source. Default-branch retirement is limited to the previous `target_reference`.
- `sync-worker`: Load `snyk.migrateIgnores` (default `true`). A GitHub updated event re-imports when the resolved org or integration differs from the stored row. When the flag is true it copies ignores from the named ADO target, and it still does not deactivate that target.
- `sync-state`: Persist in-flight source org id, source target id, and migration status so a retry can finish the copy after `snykTargetId` points at the new target.
- `observability`: Structured logs for ignore copy skipped, succeeded, and failed.

## Impact

- **Code:** Snyk v1 ignore read/write in `src/snyk/`, lifecycle ordering in `src/worker/lifecycle.py`, project listing by `target_reference`, and idempotency when the stored org or integration changes.
- **APIs:** `GET /v1/org/{orgId}/project/{projectId}/ignores` and `POST /v1/org/{orgId}/project/{projectId}/ignore/{issueId}`. The token must be allowed to read ignores in the source org and create them in the destination org.
- **State:** New in-flight fields on the repository row, cleared when the migration attempt finishes.
- **Docs:** `CONFIGURATION.md` lifecycle table and a project-ignore section. `openspec/SPEC.md` gains the capability row only when this change is archived.
- **Config:** `snyk.migrateIgnores`, default `true`, shown in `data/config.yaml.example`. `false` skips the copy only.
