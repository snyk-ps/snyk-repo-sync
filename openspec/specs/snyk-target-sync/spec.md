## Purpose

Snyk Import, target deactivation, project tagging, import-job polling, and rate-limit backoff for ADO and GitHub repository lifecycle sync.
## Requirements
### Requirement: ADO-to-Snyk mapping
For ADO events, the service MUST map ADO Project → Snyk Org (1:1), ADO Repository → Snyk Target, and ADO `repositoryId` → Snyk project tag (via Projects API).

#### Scenario: New ADO repository import
- **WHEN** an ADO repository is imported
- **THEN** a Snyk target is created under the mapped org/integration and the ADO `repositoryId` is applied as a project tag

### Requirement: GitHub-to-Snyk mapping
For GitHub events, the service MUST map GitHub Org → Snyk Org (1:1), GitHub Repository → Snyk Target, and GitHub numeric `repositoryId` → Snyk project tag (via Projects API).

#### Scenario: New GitHub repository import
- **WHEN** a GitHub repository is imported
- **THEN** a Snyk target is created under the mapped org/integration and the GitHub repository ID is applied as a project tag

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

### Requirement: No ignore migration
When deactivating and re-importing (rename or default branch change), issue ignores MUST NOT be migrated; this matches Repo Content Sync rename limitations.

#### Scenario: Repo rename
- **WHEN** the old target is deactivated and a new target is imported
- **THEN** prior issue ignores are not copied to the new target

### Requirement: Required Snyk API operations
The integration MUST support: Import API (trigger + poll), Targets API (deactivate, delete, list), and integration listing for ADO and GitHub integration resolution.

Project tagging via the Projects API is deferred to the `snyk-project-tagging` follow-up change and MUST NOT be called in this implementation slice.

#### Scenario: Repo rename flow without tagging
- **WHEN** a rename is processed in this slice
- **THEN** the old target is removed per configured removal mode, a new target is imported on the new name, and project tagging is not performed

### Requirement: Credential scope
Snyk operations MUST use a token with permissions for import, deactivate, delete (when configured), list targets, and list integrations, retrieved from Key Vault or container secrets via the `SNYK_TOKEN` environment variable.

#### Scenario: Worker startup
- **WHEN** the worker needs Snyk access
- **THEN** it retrieves the token from the configured secret store without logging the secret

### Requirement: Async import job completion
A repository MUST NOT be treated as synced until the Snyk import job completes successfully. Sync completion in this slice is defined by `importStatus=complete` and a populated `snykTargetId` on the repository row.

#### Scenario: Import in progress
- **WHEN** Snyk returns an in-progress import job
- **THEN** the worker sets `importStatus=pending` and `importJobId` on repository state and schedules a follow-up message rather than blocking the receive loop

#### Scenario: Import job failed
- **WHEN** the import job fails
- **THEN** the worker sets `importStatus=failed`, logs structured failure context including job id, and retries via scheduled follow-up until max retries or DLQ

#### Scenario: Import job succeeded
- **WHEN** the import job succeeds
- **THEN** the worker sets `importStatus=complete`, retains `importJobId` for audit, resolves and sets `snykTargetId` via the REST Targets API when not already in state, and does not call the Projects API for tagging

### Requirement: Import failure logging
Import failures MUST be logged with structured fields: `source`, scope id, repository id, Snyk org id, import job id, and failure reason. Logs MUST NOT contain secrets.

#### Scenario: Failed import job
- **WHEN** Snyk reports an import job failure
- **THEN** a structured error log is emitted suitable for Dynatrace alerting

