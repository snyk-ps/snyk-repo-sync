## MODIFIED Requirements

### Requirement: Table name and keys
Sync state MUST be stored in Azure Table Storage table `SnykSyncState` with `PartitionKey = {source}:{scopeId}` where `source` is `ado` or `github`, and `RowKey = {repositoryId}`. Operator scope-mapping rules MUST NOT be stored in Table Storage. A repository row MAY store the resolved `snykOrgId` and `snykIntegrationType` for that repository. Scope mapping rules remain owned by the `scope-mapping` capability.

#### Scenario: ADO repository partition
- **WHEN** repository state is stored for an ADO project
- **THEN** the partition key is `ado:{projectId}` and the row key is the ADO repository id

#### Scenario: GitHub repository partition
- **WHEN** repository state is stored for a GitHub organization-owned repository
- **THEN** the partition key is `github:{orgLogin}` where `orgLogin` is the GitHub organization login (`repository.owner.login`) and the row key is the GitHub repository id as a string

### Requirement: Repository state schema
Each repository row MUST store: `repoName`, `snykTargetId`, `defaultBranch`, `status`, `desiredStateHash`, `lastEventId`, `tagApplied`, `importJobId`, and `importStatus`.

Each repository row MAY store `snykOrgId` and `snykIntegrationType` as strings. A missing or blank `snykOrgId` MUST be treated as no stored Snyk org. When `snykOrgId` is non-empty, `snykIntegrationType` MUST be one of `azure-repos`, `github`, `github-cloud-app`, `github-server-app`, or `github-enterprise`.

`importStatus` MUST be one of: `pending`, `failed`, `complete`.

`snykTargetId` MUST NOT be written until import job completion. In this implementation slice, `tagApplied` MUST remain `false` (project tagging deferred).

After successful import, `importJobId` MUST be retained on the repository row for audit. A subsequent import MUST overwrite `importJobId` with the new job id while that job is pending.

#### Scenario: Import initiated
- **WHEN** a Snyk import job is started
- **THEN** the row is upserted with `importJobId`, `importStatus=pending`, and `tagApplied=false`

#### Scenario: Import completes with audit retention
- **WHEN** import job succeeds in this slice
- **THEN** the row is upserted with `importStatus=complete`, `importJobId` retained, `snykTargetId` set, and `tagApplied=false`

#### Scenario: After successful import (legacy scenario updated)
- **WHEN** import succeeds in this slice
- **THEN** the repository row is upserted with current target id, branch, status, hash, event id, retained import job id, and `importStatus=complete`

#### Scenario: Import failed
- **WHEN** import job fails
- **THEN** the row is upserted with `importStatus=failed` and the current `importJobId`

#### Scenario: Resolved org id round-trip
- **WHEN** a repository row is written with `snykOrgId` and `snykIntegrationType` and then read back
- **THEN** both properties are present as strings

#### Scenario: Row without a stored org id
- **WHEN** a repository row has no `snykOrgId` property
- **THEN** readers treat the stored Snyk org as absent
