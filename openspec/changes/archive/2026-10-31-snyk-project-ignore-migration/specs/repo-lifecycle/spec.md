## MODIFIED Requirements

### Requirement: Repo renamed
On repository renamed, when the new name does NOT match ignore policy, the service MUST snapshot the previous target, import under the new name, poll until import job completion, copy or skip v1 project ignores per `snyk-project-ignore-migration`, and only then remove the previous target per configured `snyk.targetRemoval.onRename` (default deactivate). Project tagging is deferred.

When the new name matches ignore policy, the service MUST remove the existing target per `snyk.targetRemoval.onIgnore`, MUST NOT import under the new name, and MUST complete the message.

#### Scenario: Repository rename in ADO with deactivation
- **WHEN** an audit-stream repo-renamed event with `source: "ado"` is processed, the new name does not match ignore policy, and removal mode is `deactivate`
- **THEN** a new import is started on the new name, v1 project ignores are copied or skipped, the old Snyk target is then deactivated, and state reflects pending then complete import status

#### Scenario: Repository rename in ADO with deletion
- **WHEN** an audit-stream repo-renamed event is processed, the new name does not match ignore policy, and `snyk.targetRemoval.onRename` is `delete`
- **THEN** the new name is imported and v1 project ignores are copied or skipped before the old Snyk target is deleted

#### Scenario: Repository rename in GitHub
- **WHEN** a repo-renamed event with `source: "github"` is processed and the new name does not match ignore policy
- **THEN** a new target is imported with async job polling, v1 project ignores are copied or skipped, and the old target is then removed per configured removal mode

#### Scenario: Rename into ignore policy
- **WHEN** a repo-renamed event produces a new name that matches ignore policy
- **THEN** the worker removes the existing target per `snyk.targetRemoval.onIgnore` and does not import the new name

### Requirement: Default branch changed
On default branch change, when a prior default branch is known and ignore policy does NOT apply, the service MUST import the new default branch onto the existing Snyk target, poll until import job completion, copy or skip v1 project ignores from projects whose `target_reference` is the previous branch onto projects whose `target_reference` is the new branch, and only then retire the previous branch's projects per configured `snyk.targetRemoval.onDefaultBranchChange` (default deactivate). The target MUST remain. Project tagging is deferred.

When ignore policy applies, the service MUST remove the existing target per `snyk.targetRemoval.onIgnore` if active, MUST NOT re-import, and MUST complete the message.

For `source: ado`, when `previousDefaultBranch` is absent, the worker MUST NOT perform sync actions.

#### Scenario: ADO default branch update via audit stream
- **WHEN** an audit-stream default-branch-changed event with `source: "ado"` and a prior default branch is processed and ignore policy does not apply
- **THEN** the new default branch is imported on the existing target, v1 project ignores are copied or skipped from the previous branch's projects, and only those previous-branch projects are retired

#### Scenario: ADO first default branch only
- **WHEN** an audit-stream default-branch-changed event omits `previousDefaultBranch`
- **THEN** the worker completes without project retirement or import

#### Scenario: GitHub default branch update via webhook
- **WHEN** a default-branch-changed event with `source: "github"` is processed with a prior default branch and ignore policy does not apply
- **THEN** the new default branch is imported on the existing target, v1 project ignores are copied or skipped, and only the previous branch's projects are retired

#### Scenario: Default branch change on ignored repo
- **WHEN** a default-branch-changed event with a prior default branch is processed for a repository matching ignore policy
- **THEN** the worker removes the existing target per `snyk.targetRemoval.onIgnore` if active and does not re-import

### Requirement: Provider-neutral lifecycle actions
Lifecycle handlers MUST apply the same create, rename, default-branch-changed, and delete actions regardless of `source`, subject to ignore policy, scope configuration, and configured target removal mode.

#### Scenario: Shared removal-on-rename behavior
- **WHEN** a rename event is processed for either ADO or GitHub
- **THEN** a new target is imported with async job polling, v1 project ignores are copied or skipped, and the old target is then removed per configured removal mode

### Requirement: GitHub default branch change without payload previous branch
For `source: github` default-branch-changed events, the worker MUST NOT skip lifecycle sync solely because `previousDefaultBranch` is absent from the normalized payload. The worker MUST resolve the prior branch using sync-state `defaultBranch` and/or REST project `target_reference` values on the stored target, scoped to the mapped GitHub integration type.

The old and new branches MUST be `target_reference` values on one Snyk target. The worker MUST NOT delete that target while retiring the previous branch.

#### Scenario: GitHub branch change with state
- **WHEN** a GitHub default-branch-changed event is processed and sync state contains `defaultBranch` or `snykTargetId` for the same repository id
- **THEN** the worker imports the new default branch on that target, copies or skips v1 project ignores, and retires only the previous branch's projects

#### Scenario: GitHub edited webhook maps to branch change
- **WHEN** a parsed or raw GitHub message has `action: edited` and `changes.default_branch.from`
- **THEN** the worker treats the event as default-branch-changed and uses `from` as the prior branch for project retirement

### Requirement: GitHub rename previous name resolution
For `source: github` repo-renamed events, the worker MUST resolve the previous repository name for old-target lookup using, in order: `payload.previousRepoName` from `changes.repository.name.from` when present, then sync-state `repoName` for the same `repositoryId`, then proceed with import under the new name only while logging that the previous name was unknown.

When the previous name cannot be resolved, the worker MUST NOT dead-letter solely for missing `previousRepoName`; it MUST NOT remove a Snyk target via REST unless the old target id or name is resolved. When the previous target is resolved, the worker MUST import the new name and finish v1 project-ignore migration before removing that target.

#### Scenario: GitHub rename with changes.from
- **WHEN** a GitHub renamed event includes `changes.repository.name.from`
- **THEN** the worker imports the new name, copies or skips v1 project ignores, and then removes the target for the previous name per configured removal mode

#### Scenario: GitHub rename without from but with state
- **WHEN** a GitHub renamed event omits `changes.repository.name.from` and sync state has `repoName` for the repository id
- **THEN** the worker uses stored `repoName` as the previous name, imports the new name, and removes the previous target only after v1 project-ignore migration succeeds or is skipped

#### Scenario: GitHub rename without from or state
- **WHEN** a GitHub renamed event omits `changes.repository.name.from` and no sync state exists
- **THEN** the worker imports under the new name, logs that the previous name was unknown, and does not remove a target via REST lookup
