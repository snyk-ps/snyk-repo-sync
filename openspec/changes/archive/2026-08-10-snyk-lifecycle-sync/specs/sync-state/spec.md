## MODIFIED Requirements

### Requirement: Repository state schema
Each repository row MUST store: `repoName`, `snykTargetId`, `defaultBranch`, `status`, `desiredStateHash`, `lastEventId`, `tagApplied`, `importJobId`, and `importStatus`.

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
