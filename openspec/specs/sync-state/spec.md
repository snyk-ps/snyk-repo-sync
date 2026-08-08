## Purpose

Azure Table Storage schema and access patterns for per-repository sync state (idempotency, target tracking, and lifecycle bookkeeping). Scope-to-Snyk mapping is owned by the `scope-mapping` capability and operator config — not Table Storage.

## Requirements

### Requirement: Table name and keys
Sync state MUST be stored in Azure Table Storage table `SnykSyncState` with `PartitionKey = {source}:{scopeId}` where `source` is `ado` or `github`, and `RowKey = {repositoryId}`.

#### Scenario: ADO repository partition
- **WHEN** repository state is stored for an ADO project
- **THEN** the partition key is `ado:{projectId}` and the row key is the ADO repository id

#### Scenario: GitHub repository partition
- **WHEN** repository state is stored for a GitHub org
- **THEN** the partition key is `github:{orgId}` and the row key is the GitHub repository id

### Requirement: Repository state schema
Each repository row MUST store: `repoName`, `snykTargetId`, `defaultBranch`, `status`, `desiredStateHash`, `lastEventId`, and `tagApplied`.

#### Scenario: After successful import
- **WHEN** import and tagging succeed
- **THEN** the repository row is upserted with current target id, branch, status, hash, and event id

### Requirement: Ignore list persistence
When the ignore-list JSON file is successfully retrieved, its contents MUST be persisted in state for use by the worker and scheduled ignore job.

#### Scenario: Ignore list refresh
- **WHEN** the scheduled job reads an updated ignore-list JSON file
- **THEN** the persisted ignore list in state is updated
