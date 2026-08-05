## Purpose

Azure Table Storage schema and access patterns for scope metadata (ADO project or GitHub org) and per-repository sync state.

## Requirements

### Requirement: Table name and keys
Sync state MUST be stored in Azure Table Storage table `SnykSyncState` with `PartitionKey = {source}:{scopeId}` where `source` is `ado` or `github`, and `RowKey = _meta` (scope config) or `{repositoryId}` (repository).

#### Scenario: ADO project bootstrap row
- **WHEN** an operator onboards an ADO project
- **THEN** a `_meta` row exists under partition `ado:{projectId}`

#### Scenario: GitHub org bootstrap row
- **WHEN** an operator onboards a GitHub org
- **THEN** a `_meta` row exists under partition `github:{orgId}`

### Requirement: ADO scope metadata schema
The `_meta` row for ADO scopes MUST store: `snykOrgId`, `integrationId`, `integrationType: ado`, `exclusionGlobs`, `adoProjectName`, and `enabled`.

#### Scenario: Worker reads ADO project config
- **WHEN** the worker processes any repo event for an ADO project
- **THEN** it loads `_meta` from `ado:{scopeId}` to obtain Snyk org, integration, and exclusion settings

### Requirement: GitHub scope metadata schema
The `_meta` row for GitHub scopes MUST store: `snykOrgId`, `integrationId`, `integrationType: github`, `exclusionGlobs`, `githubOrgName`, and `enabled`.

#### Scenario: Worker reads GitHub org config
- **WHEN** the worker processes any repo event for a GitHub org
- **THEN** it loads `_meta` from `github:{scopeId}` to obtain Snyk org, integration, and exclusion settings

### Requirement: Repository state schema
Each repository row MUST store: `repoName`, `snykTargetId`, `defaultBranch`, `status`, `desiredStateHash`, `lastEventId`, and `tagApplied`.

#### Scenario: After successful import
- **WHEN** import and tagging succeed
- **THEN** the repository row is upserted with current target id, branch, status, hash, and event id

### Requirement: Manual scope onboarding
New scope onboarding (ADO project or GitHub org) MUST be performed by manually creating the `_meta` row (and Snyk org/integration as needed); automated scope-created onboarding is out of scope.

#### Scenario: New scope without _meta
- **WHEN** events arrive before `_meta` exists
- **THEN** processing fails per sync-worker unknown-scope handling (DLQ + alert)

### Requirement: Ignore list persistence
When the ignore-list JSON file is successfully retrieved, its contents MUST be persisted in state for use by the worker and scheduled ignore job.

#### Scenario: Ignore list refresh
- **WHEN** the scheduled job reads an updated ignore-list JSON file
- **THEN** the persisted ignore list in state is updated
