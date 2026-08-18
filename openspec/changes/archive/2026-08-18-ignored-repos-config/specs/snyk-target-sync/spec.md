## MODIFIED Requirements

### Requirement: Deactivate over delete
Target removal mode MUST be configurable in operator config under `snyk.targetRemoval` for repository rename, default branch change, repository deletion, and ignored-repository enforcement. Allowed values: `deactivate` or `delete`. Default MUST be `deactivate` when unset.

Keys: `onRename`, `onDefaultBranchChange`, `onRepoDelete`, and `onIgnore`.

When removal mode is `deactivate`, the integration MUST deactivate every Snyk project associated with the target via the v1 Projects API (`POST /v1/org/{orgId}/project/{projectId}/deactivate`). When removal mode is `delete`, the integration MUST delete the target via the REST Targets API (`DELETE /rest/orgs/{org_id}/targets/{target_id}`).

Re-import flows (rename, default branch change) MUST resolve the old target id, remove it successfully, and only then start a new import. Removal failures MUST NOT proceed to import.

#### Scenario: Resolve target id after import
- **WHEN** an import job completes but repository state has no `snykTargetId`
- **THEN** the worker resolves the target id via the REST Targets API and persists it before marking import complete

#### Scenario: Resolve target id before removal
- **WHEN** a rename, default branch change, or delete event is processed and `snykTargetId` is empty in state
- **THEN** the worker resolves the target id via REST lookup using the appropriate repository name and branch for the old target

#### Scenario: Reimport blocked on removal failure
- **WHEN** target removal fails during rename or default branch change
- **THEN** the worker does not start a new import and surfaces the error for retry or DLQ

#### Scenario: Default removal mode
- **WHEN** `snyk.targetRemoval` is absent
- **THEN** rename, default branch change, repo delete, and ignore enforcement all use target deactivation

#### Scenario: Delete on repo removal
- **WHEN** `snyk.targetRemoval.onRepoDelete` is `delete` and a repo-deleted event is processed
- **THEN** the Snyk target is hard-deleted and repository state reflects inactive status with no active target id

#### Scenario: Delete before re-import on rename
- **WHEN** `snyk.targetRemoval.onRename` is `delete` and a repo-renamed event is processed
- **THEN** the old Snyk target is deleted before import of the new target name

#### Scenario: Deactivate before re-import on default branch change
- **WHEN** `snyk.targetRemoval.onDefaultBranchChange` is `deactivate` and a default-branch-changed event with a prior default branch is processed
- **THEN** the old Snyk target is deactivated before re-import on the new default branch

#### Scenario: Ignored repo with active target
- **WHEN** ignore policy matches a repository with an active synced target
- **THEN** the target is removed per `snyk.targetRemoval.onIgnore`

#### Scenario: Delete on ignore match
- **WHEN** `snyk.targetRemoval.onIgnore` is `delete` and a repository matches ignore policy with an active target
- **THEN** the Snyk target is hard-deleted and repository state reflects inactive status
