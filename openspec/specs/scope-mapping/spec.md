## Purpose

Resolve provider scopes (ADO project or GitHub org) to Snyk organizations and integrations via operator configuration and the Snyk API. Scope mapping replaces manual Table Storage `_meta` onboarding.
## Requirements
### Requirement: Config-based scope to Snyk org mapping
Operators MUST declare scope-to-Snyk-org mappings in operator config (`config.yaml`). ADO mappings MUST use ADO project name as the lookup key under the `azure-repos` integration type section. GitHub mappings MUST use GitHub organization name (login) as the lookup key under a GitHub integration type section (`github`, `github-cloud`, `github-server`, or `github-enterprise`).

The worker MUST load and validate scope mapping entries at startup. Each mapping entry MUST include a non-empty `snykOrgId`. Duplicate lookup keys within a source MUST cause startup failure. Legacy top-level key `ado` MUST be rejected at startup.

#### Scenario: Mapped ADO project
- **WHEN** the worker processes an ADO event for a project name present in `scopeMapping.azure-repos`
- **THEN** it resolves the target Snyk organization id from config

#### Scenario: Mapped GitHub org
- **WHEN** the worker processes a GitHub event for an org name present in a configured GitHub integration type section
- **THEN** it resolves the target Snyk organization id from config

#### Scenario: Invalid duplicate ADO project name
- **WHEN** operator config contains two `scopeMapping.azure-repos` entries with the same `projectName`
- **THEN** the worker exits at startup with a clear configuration error

#### Scenario: Legacy ADO scope mapping key
- **WHEN** operator config contains `scopeMapping.ado`
- **THEN** the worker exits at startup with a clear configuration error directing operators to `azure-repos`

### Requirement: Snyk integration type as scope mapping section key
Scope mapping sections MUST be keyed by Snyk integration type, not provider source names. Allowed top-level keys under `scopeMapping` (other than `defaultSnykOrgId`) are:

| Section key | Provider source | Entry shape |
| ----------- | --------------- | ----------- |
| `azure-repos` | ADO | `projectName`, `snykOrgId`, optional `snykIntegrationId` |
| `github` | GitHub | `orgName`, `snykOrgId`, optional `snykIntegrationId` |
| `github-cloud` | GitHub | same as `github` |
| `github-server` | GitHub | same as `github` |
| `github-enterprise` | GitHub | same as `github` |

The integration type used for Snyk API lookup MUST be the section key. Unknown section keys MUST cause startup failure.

When `defaultSnykOrgId` is used without an explicit scope entry, the worker MUST use `azure-repos` for ADO events. For GitHub events it MUST use `github` unless exactly one GitHub integration type section is configured, in which case that type MUST be used.

#### Scenario: ADO entry under azure-repos section
- **WHEN** an ADO scope mapping entry is listed under `scopeMapping.azure-repos`
- **THEN** the worker uses `azure-repos` for integration lookup

#### Scenario: GitHub entry under github-enterprise section
- **WHEN** a GitHub scope mapping entry is listed under `scopeMapping.github-enterprise`
- **THEN** the worker resolves the integration whose Snyk type is `github-enterprise`

#### Scenario: Invalid top-level scope mapping key
- **WHEN** operator config contains `scopeMapping.ado` or an unsupported integration type key
- **THEN** the worker exits at startup with a clear configuration error

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

### Requirement: Unmapped scope handling
When no config mapping exists for a scope name, the worker MUST log the failure. Configuration MAY specify an optional default Snyk organization id for unmapped scopes.

Unmapped scopes MUST NOT dead-letter the message.

#### Scenario: Unmapped ADO project without default
- **WHEN** an ADO event arrives for a project name with no config mapping and no default org is configured
- **THEN** the worker logs the unmapped scope and does not perform Snyk side effects

#### Scenario: Unmapped scope with default org
- **WHEN** an ADO or GitHub event arrives for an unmapped scope name and `defaultSnykOrgId` is configured
- **THEN** the worker uses the default Snyk organization and default integration type for the provider source

### Requirement: Optional integration id in operator config
Scope mapping list entries MAY include an optional `snykIntegrationId` string. When present, the value MUST be non-empty. Duplicate validation rules for scope entries otherwise unchanged.

#### Scenario: Config with integration id
- **WHEN** operator config includes `snykIntegrationId` on an ADO project entry under `azure-repos`
- **THEN** the worker uses that integration id for Snyk actions targeting that scope

