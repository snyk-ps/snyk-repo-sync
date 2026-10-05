## MODIFIED Requirements

### Requirement: Import branch resolution
Before starting a Snyk import for ADO repository lifecycle actions, the worker MUST include `target.branch` in the import payload. When the normalized event provides `defaultBranch`, that value MUST be used. When the event does not provide a default branch, the worker MUST resolve the branch via ADO Git REST API using `ADO_PAT` and configured `ado.organization`. The worker MUST NOT infer a hardcoded branch name such as `main`. Repository state `defaultBranch` MUST match the branch used in the import payload.

For GitHub repository lifecycle actions, the worker MUST use the normalized repository default branch (`payload.defaultBranch` or repository default branch field from normalization). The worker MUST NOT call ADO Git REST API for GitHub events.

#### Scenario: Repo created with audit default branch
- **WHEN** a repo-created ADO event includes `payload.defaultBranch`
- **THEN** the worker starts import with that branch and does not call ADO REST for branch lookup

#### Scenario: Repo renamed without branch in event
- **WHEN** a repo-renamed ADO event omits `defaultBranch` and existing sync state has no stored branch
- **THEN** the worker resolves the repository default branch via ADO Git REST API before starting import and stores that branch in repository state

#### Scenario: GitHub repo created with default branch in event
- **WHEN** a repo-created GitHub event includes a default branch from normalization
- **THEN** the worker starts import with that branch and does not call ADO REST

## ADDED Requirements

### Requirement: GitHub default branch change without payload previous branch
For `source: github` default-branch-changed events, the worker MUST NOT skip lifecycle sync solely because `previousDefaultBranch` is absent from the normalized payload. The worker MUST resolve the prior Snyk target using sync-state `snykTargetId`, sync-state `defaultBranch`, and/or REST target lookup with org login, repository name, and prior branch name when known, scoped to the mapped GitHub integration type.

The service MUST NOT support multiple active Snyk targets for different branches of the same GitHub repository under the mapped integration in this implementation slice.

#### Scenario: GitHub branch change with state
- **WHEN** a GitHub default-branch-changed event is processed and sync state contains `defaultBranch` or `snykTargetId` for the same repository id
- **THEN** the worker removes the prior target per configured removal mode and re-imports on the new default branch

#### Scenario: GitHub edited webhook maps to branch change
- **WHEN** a parsed or raw GitHub message has `action: edited` and `changes.default_branch.from`
- **THEN** the worker treats the event as default-branch-changed and uses `from` as the prior branch when needed for target lookup

### Requirement: GitHub rename previous name resolution
For `source: github` repo-renamed events, the worker MUST resolve the previous repository name for old-target lookup using, in order: `payload.previousRepoName` from `changes.repository.name.from` when present, then sync-state `repoName` for the same `repositoryId`, then proceed with import under the new name only while logging that the previous name was unknown.

When the previous name cannot be resolved, the worker MUST NOT dead-letter solely for missing `previousRepoName`; it MUST NOT remove a Snyk target via REST unless the old target id or name is resolved.

#### Scenario: GitHub rename with changes.from
- **WHEN** a GitHub renamed event includes `changes.repository.name.from`
- **THEN** the worker removes the target for the previous name per configured removal mode before importing the new name

#### Scenario: GitHub rename without from but with state
- **WHEN** a GitHub renamed event omits `changes.repository.name.from` and sync state has `repoName` for the repository id
- **THEN** the worker uses stored `repoName` as the previous name for target removal before import

#### Scenario: GitHub rename without from or state
- **WHEN** a GitHub renamed event omits `changes.repository.name.from` and no sync state exists
- **THEN** the worker imports under the new name, logs that the previous name was unknown, and does not remove a target via REST lookup
