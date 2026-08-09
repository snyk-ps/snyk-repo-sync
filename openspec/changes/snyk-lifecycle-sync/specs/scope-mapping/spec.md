## MODIFIED Requirements

### Requirement: Integration resolution via Snyk API
After resolving a Snyk organization id, the worker MUST retrieve the corresponding ADO or GitHub integration id. Integration ids MUST NOT be stored in sync-state Table Storage.

Each scope mapping entry MAY optionally include `snykIntegrationId`. When set, the worker MUST use the configured id. When omitted, or when Snyk returns an invalid integration response for a configured id, the worker MUST resolve the integration id via the Snyk API and MAY cache the result in process memory for the lifetime of the worker process.

#### Scenario: ADO integration lookup via API
- **WHEN** an ADO repository lifecycle action requires import or target removal and no `snykIntegrationId` is configured
- **THEN** the worker resolves the ADO integration id for the mapped Snyk org via API

#### Scenario: ADO integration from config
- **WHEN** an ADO scope mapping entry includes `snykIntegrationId`
- **THEN** the worker uses the configured integration id without calling the integrations list API

#### Scenario: GitHub integration lookup via API
- **WHEN** a GitHub repository lifecycle action requires import or target removal and no `snykIntegrationId` is configured
- **THEN** the worker resolves the GitHub integration id for the mapped Snyk org via API

#### Scenario: Stale configured integration id
- **WHEN** a configured `snykIntegrationId` is rejected by Snyk as invalid
- **THEN** the worker logs a warning, resolves the integration id via API once, and updates its process-local cache

## ADDED Requirements

### Requirement: Optional integration id in operator config
Scope mapping list entries MAY include an optional non-empty `snykIntegrationId` string. Duplicate validation rules for scope entries otherwise unchanged.

#### Scenario: Config with integration id
- **WHEN** operator config includes `snykIntegrationId` on an ADO project entry
- **THEN** the worker uses that integration id for Snyk actions targeting that scope
