## ADDED Requirements

### Requirement: RBAC authentication
Sync state access MUST authenticate to Azure Table Storage using `DefaultAzureCredential`. The application MUST NOT use storage account keys, connection strings, or shared access signatures.

The runtime identity MUST be granted the Azure built-in role **Storage Table Data Contributor** (role ID `0a9a7e1f-b9d0-4cc4-a60d-0319b160aaa3`) on the target storage account or table scope.

#### Scenario: Production managed identity
- **WHEN** the worker runs on Azure Container Apps with a managed identity assigned Storage Table Data Contributor
- **THEN** it authenticates to Table Storage without storage secrets

#### Scenario: Local development principal
- **WHEN** a developer runs the worker locally after `az login` (or with a service principal) with Storage Table Data Contributor
- **THEN** Table Storage operations succeed against the configured account

### Requirement: Operator config and environment overrides for storage settings
Storage settings MUST be readable from operator config file keys `syncState.storageAccountEndpoint` and optional `syncState.tableName`. The worker MUST accept the config path via CLI flag `--config` (default `data/config.yaml`). Settings MAY be overridden by environment variables; env values MUST take precedence when set.

| Setting | Config key | Env var override |
| ------- | ---------- | ---------------- |
| Table service endpoint | `syncState.storageAccountEndpoint` | `SYNC_STATE_STORAGE_ACCOUNT_ENDPOINT` |
| Table name | `syncState.tableName` | `SYNC_STATE_TABLE_NAME` |

#### Scenario: Default table name
- **WHEN** `syncState.tableName` and `SYNC_STATE_TABLE_NAME` are both unset
- **THEN** sync state uses table `SnykSyncState`

#### Scenario: Custom table name via config
- **WHEN** `syncState.tableName` is set to `CustomerSyncState`
- **THEN** sync state uses table `CustomerSyncState`

#### Scenario: Table name overridden by env
- **WHEN** `syncState.tableName` is `SnykSyncState` and `SYNC_STATE_TABLE_NAME` is `DevSyncState`
- **THEN** sync state uses table `DevSyncState`

#### Scenario: Missing storage endpoint after config/env merge
- **WHEN** `syncState.storageAccountEndpoint` and `SYNC_STATE_STORAGE_ACCOUNT_ENDPOINT` are both absent
- **THEN** the worker exits at startup with a clear error

### Requirement: Table auto-provisioning
On startup, the application MUST call `create_table_if_not_exists` for the configured table name. This MUST NOT create storage accounts or Service Bus resources.

#### Scenario: First startup with default table
- **WHEN** the worker starts and table `SnykSyncState` does not exist and the identity has Storage Table Data Contributor
- **THEN** the table is created before message processing begins

#### Scenario: Table already exists
- **WHEN** the worker starts and the configured table already exists
- **THEN** startup succeeds without error

### Requirement: Repository entity property types
Repository rows MUST persist spec fields as Azure Table entity properties: string fields as strings and `tagApplied` as a boolean.

#### Scenario: Repository row round-trip
- **WHEN** a repository row is written and read back
- **THEN** all required repository fields are present with correct types

## MODIFIED Requirements

### Requirement: Table name and keys
Sync state MUST be stored in Azure Table Storage table `SnykSyncState` with `PartitionKey = {source}:{scopeId}` where `source` is `ado` or `github`, and `RowKey = {repositoryId}`. Scope configuration MUST NOT be stored in Table Storage; scope mapping is owned by the `scope-mapping` capability.

#### Scenario: ADO repository partition
- **WHEN** repository state is stored for an ADO project
- **THEN** the partition key is `ado:{projectId}` and the row key is the ADO repository id

#### Scenario: GitHub repository partition
- **WHEN** repository state is stored for a GitHub org
- **THEN** the partition key is `github:{orgId}` and the row key is the GitHub repository id