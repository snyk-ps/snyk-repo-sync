## MODIFIED Requirements

### Requirement: Table name and keys
Sync state MUST be stored in Azure Table Storage table `SnykSyncState` with `PartitionKey = {source}:{scopeId}` where `source` is `ado` or `github`, and `RowKey = {repositoryId}`. Scope configuration MUST NOT be stored in Table Storage; scope mapping is owned by the `scope-mapping` capability.

#### Scenario: ADO repository partition
- **WHEN** repository state is stored for an ADO project
- **THEN** the partition key is `ado:{projectId}` and the row key is the ADO repository id

#### Scenario: GitHub repository partition
- **WHEN** repository state is stored for a GitHub organization-owned repository
- **THEN** the partition key is `github:{orgLogin}` where `orgLogin` is the GitHub organization login (`repository.owner.login`) and the row key is the GitHub repository id as a string
