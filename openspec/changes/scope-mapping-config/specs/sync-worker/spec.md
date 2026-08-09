## RENAMED Requirements

- FROM: `### Requirement: Slice-3 ADO normalization with sync table only`
- TO: `### Requirement: Slice-4 ADO normalization with scope mapping`

## MODIFIED Requirements

### Requirement: Slice-4 ADO normalization with scope mapping
After successful ADO lifecycle normalization, the worker MUST resolve scope mapping per the `scope-mapping` capability using `ado.projectName` as the lookup key, log the resolution outcome (mapped, default, or unmapped), and complete the message without repository state reads/writes or Snyk API side effects.

The sync-state table MUST be ensured on startup for use by follow-up changes.

GitHub queue messages MUST be completed without normalization or sync side effects until GitHub normalization is implemented. GitHub scope mapping entries MUST be loaded from config at startup for use by follow-up changes.

#### Scenario: Valid ADO message with mapped project
- **WHEN** the worker normalizes an ADO lifecycle message whose `ado.projectName` matches a config entry
- **THEN** it logs the resolved `snykOrgId` and `exclusionGlobs`, then completes the message

#### Scenario: Valid ADO message with unmapped project
- **WHEN** the worker normalizes an ADO lifecycle message whose `ado.projectName` has no config entry and no `defaultSnykOrgId` is configured
- **THEN** it logs an unmapped-scope warning and completes the message

#### Scenario: Valid ADO message with default org
- **WHEN** the worker normalizes an ADO lifecycle message for an unmapped project and `defaultSnykOrgId` is configured
- **THEN** it logs use of the default Snyk org id and completes the message

#### Scenario: Valid GitHub message in slice 4
- **WHEN** the worker parses a valid GitHub webhook queue message
- **THEN** it completes the message without normalization or scope resolution
