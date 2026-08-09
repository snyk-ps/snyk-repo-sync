## Purpose

Snyk Import, target deactivation, project tagging, import-job polling, and rate-limit backoff for ADO and GitHub repository lifecycle sync.

## Requirements

### Requirement: ADO-to-Snyk mapping
For ADO events, the service MUST map ADO Project → Snyk Org (1:1), ADO Repository → Snyk Target, and ADO `repositoryId` → Snyk project tag (via Projects API).

#### Scenario: New ADO repository import
- **WHEN** an ADO repository is imported
- **THEN** a Snyk target is created under the mapped org/integration and the ADO `repositoryId` is applied as a project tag

### Requirement: GitHub-to-Snyk mapping
For GitHub events, the service MUST map GitHub Org → Snyk Org (1:1), GitHub Repository → Snyk Target, and GitHub numeric `repositoryId` → Snyk project tag (via Projects API).

#### Scenario: New GitHub repository import
- **WHEN** a GitHub repository is imported
- **THEN** a Snyk target is created under the mapped org/integration and the GitHub repository ID is applied as a project tag

### Requirement: Deactivate over delete
Target removal MUST use deactivation, not hard delete.

#### Scenario: Repo deleted
- **WHEN** a repository is deleted in ADO or GitHub
- **THEN** the corresponding Snyk target is deactivated

### Requirement: No ignore migration
When deactivating and re-importing (rename or default branch change), issue ignores MUST NOT be migrated; this matches Repo Content Sync rename limitations.

#### Scenario: Repo rename
- **WHEN** the old target is deactivated and a new target is imported
- **THEN** prior issue ignores are not copied to the new target

### Requirement: Required Snyk API operations
The integration MUST support: Import API (trigger + poll), Targets API (deactivate, list), and project tagging via the Projects API.

#### Scenario: Repo rename flow
- **WHEN** a rename is processed
- **THEN** the old target is deactivated, a new target is imported on the new name, and the repository id tag is applied to the new target's projects

### Requirement: Credential scope
Snyk operations MUST use a token with permissions for import, deactivate, list targets, and project tags, retrieved from Key Vault or container secrets.

#### Scenario: Worker startup
- **WHEN** the worker needs Snyk access
- **THEN** it retrieves the token from the configured secret store without logging the secret
