## ADDED Requirements

### Requirement: Import branch resolution
Before starting a Snyk import for ADO repository lifecycle actions, the worker MUST include `target.branch` in the import payload. When the normalized event provides `defaultBranch`, that value MUST be used. When the event does not provide a default branch, the worker MUST resolve the branch via ADO Git REST API using `ADO_PAT` and configured `ado.organization`. The worker MUST NOT infer a hardcoded branch name such as `main`. Repository state `defaultBranch` MUST match the branch used in the import payload.

#### Scenario: Repo created with audit default branch
- **WHEN** a repo-created ADO event includes `payload.defaultBranch`
- **THEN** the worker starts import with that branch and does not call ADO REST for branch lookup

#### Scenario: Repo renamed without branch in event
- **WHEN** a repo-renamed ADO event omits `defaultBranch` and existing sync state has no stored branch
- **THEN** the worker resolves the repository default branch via ADO Git REST API before starting import and stores that branch in repository state

## MODIFIED Requirements

### Requirement: Repo created
On repository created, the service MUST import the repository when scope mapping resolves and ignore policy does not apply. Project tagging is deferred to the `snyk-project-tagging` follow-up change.

A repository MUST NOT be considered synced until the import job completes (`importStatus=complete`) and `snykTargetId` is set.

#### Scenario: New repo in mapped ADO project
- **WHEN** an audit-stream repo-created event with `source: "ado"` is processed for a non-ignored repository with resolved scope mapping
- **THEN** the worker triggers Snyk import, sets `importStatus=pending` on repository state, and schedules import job polling until the job completes or fails unrecoverably

#### Scenario: New repo import completes
- **WHEN** the import job for a repo-created event succeeds
- **THEN** repository state is updated with `importStatus=complete`, retained `importJobId`, and `snykTargetId`, and `tagApplied` remains `false`

#### Scenario: New repo in mapped GitHub org
- **WHEN** a repo-created event with `source: "github"` is processed for a non-ignored repository
- **THEN** the worker imports the repo and completes import job polling per the same async contract (when GitHub normalization is implemented)

### Requirement: Repo renamed
On repository renamed, the service MUST remove the old target per configured `snyk.targetRemoval.onRename` (default deactivate), import under the new name, poll until import job completion, and update repository state. Project tagging is deferred.

#### Scenario: Repository rename in ADO with deactivation
- **WHEN** an audit-stream repo-renamed event with `source: "ado"` is processed and removal mode is `deactivate`
- **THEN** the old Snyk target is deactivated, a new import is started on the new name, and state reflects pending then complete import status

#### Scenario: Repository rename in ADO with deletion
- **WHEN** an audit-stream repo-renamed event is processed and `snyk.targetRemoval.onRename` is `delete`
- **THEN** the old Snyk target is deleted before import on the new name

#### Scenario: Repository rename in GitHub
- **WHEN** a repo-renamed event with `source: "github"` is processed
- **THEN** the old target is removed per configured removal mode and a new target is imported with async job polling (when GitHub normalization is implemented)

### Requirement: Default branch changed
On default branch change, when `previousDefaultBranch` is present in the normalized payload, the service MUST remove the old target per configured `snyk.targetRemoval.onDefaultBranchChange` (default deactivate), re-import on the new default branch, and poll until import job completion. Project tagging is deferred.

When `previousDefaultBranch` is absent, the worker MUST NOT perform sync actions.

#### Scenario: ADO default branch update via audit stream
- **WHEN** an audit-stream default-branch-changed event with `source: "ado"` and a prior default branch is processed
- **THEN** the old target is removed per configured removal mode and import is repeated against the new default branch with async job polling

#### Scenario: ADO first default branch only
- **WHEN** an audit-stream default-branch-changed event omits `previousDefaultBranch`
- **THEN** the worker completes without target removal or import

#### Scenario: GitHub default branch update via webhook
- **WHEN** a default-branch-changed event with `source: "github"` is processed with a prior default branch
- **THEN** the old target is removed per configured removal mode and import is repeated with async job polling (when GitHub normalization is implemented)

### Requirement: Repo deleted
On repository deleted, the service MUST remove the corresponding Snyk target per configured `snyk.targetRemoval.onRepoDelete` (default deactivate) and update repository state to inactive.

#### Scenario: Repository removed from ADO with deactivation
- **WHEN** an audit-stream repo-deleted event with `source: "ado"` is processed and removal mode is `deactivate`
- **THEN** the Snyk target is deactivated and repository state reflects inactive status

#### Scenario: Repository removed from ADO with deletion
- **WHEN** an audit-stream repo-deleted event is processed and `snyk.targetRemoval.onRepoDelete` is `delete`
- **THEN** the Snyk target is deleted, `snykTargetId` is cleared, and repository state reflects inactive status

#### Scenario: Repository removed from GitHub
- **WHEN** a repo-deleted event with `source: "github"` is processed
- **THEN** the target is removed per configured removal mode and repository state reflects inactive status

#### Scenario: Delete while import pending
- **WHEN** a repo-deleted event arrives while `importStatus=pending`
- **THEN** the worker stops import polling, removes the target if known, and marks repository state inactive

### Requirement: Provider-neutral lifecycle actions
Lifecycle handlers MUST apply the same create, rename, default-branch-changed, and delete actions regardless of `source`, subject to ignore policy, scope configuration, and configured target removal mode.

#### Scenario: Shared removal-on-rename behavior
- **WHEN** a rename event is processed for either ADO or GitHub
- **THEN** the old target is removed per configured removal mode, a new target is imported with async job polling, and issue ignores are not migrated
