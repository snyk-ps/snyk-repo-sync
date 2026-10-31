## MODIFIED Requirements

### Requirement: Repository state schema
Each repository row MUST store: `repoName`, `snykTargetId`, `defaultBranch`, `status`, `desiredStateHash`, `lastEventId`, `tagApplied`, `importJobId`, and `importStatus`.

Each repository row MAY store `snykOrgId` and `snykIntegrationType` as strings. A missing or blank `snykOrgId` MUST be treated as no stored Snyk org. When `snykOrgId` is non-empty, `snykIntegrationType` MUST be one of `azure-repos`, `github`, `github-cloud-app`, `github-server-app`, or `github-enterprise`.

`importStatus` MUST be one of: `pending`, `failed`, `complete`.

`snykTargetId` MUST NOT be written until import job completion. In this implementation slice, `tagApplied` MUST remain `false` (project tagging deferred).

After successful import, `importJobId` MUST be retained on the repository row for audit. A subsequent import MUST overwrite `importJobId` with the new job id while that job is pending.

During v1 project-ignore migration the row MUST store `ignoreMigrationKind` (`rename`, `default_branch`, `updated`, or empty), `ignoreMigrationStatus` (`pending`, `complete`, `skipped`, or empty), `ignoreSourceOrgId`, `ignoreSourceTargetId`, and `ignoreSourceTargetReference`. The worker MUST set the kind and `ignoreMigrationStatus=pending` before import overwrites `snykTargetId` or `defaultBranch` for rename, default branch change, and a parsed GitHub updated import. The worker MUST clear these five properties when the migration attempt finishes, including the required source retirement when the event retires the source. A GitHub updated attempt MUST clear them after the copy or skip and MUST NOT use them as a standing ADO link.

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

#### Scenario: Rename snapshots the previous target before import
- **WHEN** a repo-renamed event starts an import and the previous target id is known
- **THEN** the row stores `ignoreMigrationKind=rename`, `ignoreMigrationStatus=pending`, and that previous target id before `snykTargetId` is cleared

#### Scenario: Migration fields cleared after retirement
- **WHEN** a rename or default-branch migration finishes and the required source retirement succeeds
- **THEN** `ignoreMigrationKind`, `ignoreMigrationStatus`, `ignoreSourceOrgId`, `ignoreSourceTargetId`, and `ignoreSourceTargetReference` are empty

### Requirement: Repository entity property types
Repository rows MUST persist spec fields as Azure Table entity properties: string fields as strings and `tagApplied` as a boolean. `ignoreMigrationKind`, `ignoreMigrationStatus`, `ignoreSourceOrgId`, `ignoreSourceTargetId`, and `ignoreSourceTargetReference` MUST be strings.

#### Scenario: Repository row round-trip
- **WHEN** a repository row is written and read back
- **THEN** all required repository fields are present with correct types
