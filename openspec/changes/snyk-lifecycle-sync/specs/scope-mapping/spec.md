## MODIFIED Requirements

### Requirement: Integration resolution via Snyk API
After resolving a Snyk organization id and integration type, the worker MUST retrieve the corresponding integration id. Integration ids MUST NOT be stored in sync-state Table Storage.

Each scope mapping entry MAY optionally include `snykIntegrationId`. When set, the worker MUST use the configured id. When omitted, or when Snyk returns an invalid integration response for a configured id, the worker MUST list integrations for the Snyk org via API, match by the section integration type, and MAY cache the result in process memory for the lifetime of the worker process.

Integration lookup failures MUST report the requested Snyk integration type and the integration types available in the org — not the provider source name.

#### Scenario: ADO integration lookup via API
- **WHEN** an ADO repository lifecycle action requires import or target removal, the scope is mapped under `azure-repos`, and no `snykIntegrationId` is configured
- **THEN** the worker resolves the `azure-repos` integration id for the mapped Snyk org via API

#### Scenario: ADO integration from config
- **WHEN** an ADO scope mapping entry includes `snykIntegrationId`
- **THEN** the worker uses the configured integration id without calling the integrations list API

#### Scenario: GitHub integration lookup via API
- **WHEN** a GitHub repository lifecycle action requires import or target removal and no `snykIntegrationId` is configured
- **THEN** the worker resolves the integration id matching the entry's section integration type via API

#### Scenario: Stale configured integration id
- **WHEN** a configured `snykIntegrationId` is rejected by Snyk as invalid
- **THEN** the worker logs a warning, resolves the integration id via API once using the section integration type, and updates its process-local cache

#### Scenario: Integration type not present in org
- **WHEN** no integration of the configured section type exists in the Snyk org
- **THEN** the worker reports an error naming the requested integration type and listing available Snyk integration types for the org

## ADDED Requirements

### Requirement: Snyk integration type as scope mapping section key
Scope mapping sections MUST be keyed by Snyk integration type, not provider source names. Allowed top-level keys under `scopeMapping` (other than `defaultSnykOrgId`) are `azure-repos`, `github`, `github-cloud`, `github-server`, and `github-enterprise`.

Legacy key `ado` MUST be rejected at startup with a clear error.

The integration type used for Snyk API lookup MUST be the section key. When `defaultSnykOrgId` is used without an explicit scope entry, the worker MUST use `azure-repos` for ADO and `github` for GitHub unless exactly one GitHub integration type section is configured.

#### Scenario: ADO entry under azure-repos section
- **WHEN** an ADO scope mapping entry is listed under `scopeMapping.azure-repos`
- **THEN** the worker uses `azure-repos` for integration lookup

#### Scenario: GitHub entry under github-enterprise section
- **WHEN** a GitHub scope mapping entry is listed under `scopeMapping.github-enterprise`
- **THEN** the worker resolves the integration whose Snyk type is `github-enterprise`

#### Scenario: Legacy ADO scope mapping key rejected
- **WHEN** operator config contains `scopeMapping.ado`
- **THEN** the worker exits at startup with a clear configuration error

### Requirement: Optional integration id in operator config
Scope mapping list entries MAY include an optional non-empty `snykIntegrationId` string. Duplicate validation rules for scope entries otherwise unchanged.

#### Scenario: Config with integration id
- **WHEN** operator config includes `snykIntegrationId` on an ADO project entry under `azure-repos`
- **THEN** the worker uses that integration id for Snyk actions targeting that scope
