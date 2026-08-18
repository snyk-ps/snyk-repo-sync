## ADDED Requirements

### Requirement: Ignore policy on lifecycle events
When a lifecycle event matches ignore policy, the worker MUST NOT import or re-import the repository. When an active Snyk target exists, removal MUST use `snyk.targetRemoval.onIgnore` (not `onRename` or `onDefaultBranchChange`).

#### Scenario: Rename into ignore policy
- **WHEN** a repo-renamed event produces a new name that matches ignore policy
- **THEN** the worker does not import the new name and removes the existing target per `snyk.targetRemoval.onIgnore` on that event

#### Scenario: Default branch change on ignored repo
- **WHEN** a default-branch-changed event with a prior default branch is processed for a repository matching ignore policy
- **THEN** the worker does not re-import and removes the existing target per `snyk.targetRemoval.onIgnore` if active

#### Scenario: Ignored repo created
- **WHEN** a repo-created event matches ignore policy
- **THEN** the worker completes without import regardless of `onIgnore`

## MODIFIED Requirements

### Requirement: Repo renamed
On repository renamed, when the new name does NOT match ignore policy, the service MUST remove the old target per configured `snyk.targetRemoval.onRename` (default deactivate), import under the new name, poll until import job completion, and update repository state. Project tagging is deferred.

When the new name matches ignore policy, the service MUST remove the existing target per `snyk.targetRemoval.onIgnore`, MUST NOT import under the new name, and MUST complete the message.

#### Scenario: Repository rename in ADO with deactivation
- **WHEN** an audit-stream repo-renamed event with `source: "ado"` is processed, the new name does not match ignore policy, and removal mode is `deactivate`
- **THEN** the old Snyk target is deactivated, a new import is started on the new name, and state reflects pending then complete import status

#### Scenario: Repository rename in ADO with deletion
- **WHEN** an audit-stream repo-renamed event is processed, the new name does not match ignore policy, and `snyk.targetRemoval.onRename` is `delete`
- **THEN** the old Snyk target is deleted before import on the new name

#### Scenario: Repository rename in GitHub
- **WHEN** a repo-renamed event with `source: "github"` is processed and the new name does not match ignore policy
- **THEN** the old target is removed per configured removal mode and a new target is imported with async job polling (when GitHub normalization is implemented)

#### Scenario: Rename into ignore policy
- **WHEN** a repo-renamed event produces a new name that matches ignore policy
- **THEN** the worker removes the existing target per `snyk.targetRemoval.onIgnore` and does not import the new name

### Requirement: Default branch changed
On default branch change, when `previousDefaultBranch` is present in the normalized payload and ignore policy does NOT apply, the service MUST remove the old target per configured `snyk.targetRemoval.onDefaultBranchChange` (default deactivate), re-import on the new default branch, and poll until import job completion. Project tagging is deferred.

When ignore policy applies, the service MUST remove the existing target per `snyk.targetRemoval.onIgnore` if active, MUST NOT re-import, and MUST complete the message.

When `previousDefaultBranch` is absent, the worker MUST NOT perform sync actions.

#### Scenario: ADO default branch update via audit stream
- **WHEN** an audit-stream default-branch-changed event with `source: "ado"` and a prior default branch is processed and ignore policy does not apply
- **THEN** the old target is removed per configured removal mode and import is repeated against the new default branch with async job polling

#### Scenario: ADO first default branch only
- **WHEN** an audit-stream default-branch-changed event omits `previousDefaultBranch`
- **THEN** the worker completes without target removal or import

#### Scenario: GitHub default branch update via webhook
- **WHEN** a default-branch-changed event with `source: "github"` is processed with a prior default branch and ignore policy does not apply
- **THEN** the old target is removed per configured removal mode and import is repeated with async job polling (when GitHub normalization is implemented)

#### Scenario: Default branch change on ignored repo
- **WHEN** a default-branch-changed event with a prior default branch is processed for a repository matching ignore policy
- **THEN** the worker removes the existing target per `snyk.targetRemoval.onIgnore` if active and does not re-import
