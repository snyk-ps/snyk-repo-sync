## MODIFIED Requirements

### Requirement: Config-based scope to Snyk org mapping
Operators MUST declare scope-to-Snyk-org mappings in operator config (`config.yaml`). ADO mappings MUST use ADO project name as the lookup key under the `azure-repos` integration type section. GitHub mappings MUST use GitHub organization name (login) as the lookup key under a GitHub integration type section (`github`, `github-cloud-app`, `github-server-app`, or `github-enterprise`).

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
| `github-cloud-app` | GitHub | same as `github` |
| `github-server-app` | GitHub | same as `github` |
| `github-enterprise` | GitHub | same as `github` |

The integration type used for Snyk API lookup MUST be the section key. Unknown section keys, including `github-cloud` and `github-server`, MUST cause startup failure.

When `defaultSnykOrgId` is used without an explicit scope entry, the worker MUST use `azure-repos` for ADO events. For GitHub events it MUST use `github` unless exactly one GitHub integration type section is configured, in which case that type MUST be used.

#### Scenario: ADO entry under azure-repos section
- **WHEN** an ADO scope mapping entry is listed under `scopeMapping.azure-repos`
- **THEN** the worker uses `azure-repos` for integration lookup

#### Scenario: GitHub entry under github-enterprise section
- **WHEN** a GitHub scope mapping entry is listed under `scopeMapping.github-enterprise`
- **THEN** the worker resolves the integration whose Snyk type is `github-enterprise`

#### Scenario: GitHub Cloud App section
- **WHEN** a GitHub org mapping is listed under `scopeMapping.github-cloud-app`
- **THEN** the worker uses `github-cloud-app` for Snyk integration lookup

#### Scenario: GitHub Server App section
- **WHEN** a GitHub org mapping is listed under `scopeMapping.github-server-app`
- **THEN** the worker uses `github-server-app` for Snyk integration lookup

#### Scenario: Obsolete GitHub Cloud key
- **WHEN** operator config contains `scopeMapping.github-cloud`
- **THEN** the worker exits at startup with a clear error that lists `github-cloud-app` as an allowed key

#### Scenario: Obsolete GitHub Server key
- **WHEN** operator config contains `scopeMapping.github-server`
- **THEN** the worker exits at startup with a clear error that lists `github-server-app` as an allowed key

#### Scenario: Invalid top-level scope mapping key
- **WHEN** operator config contains `scopeMapping.ado` or an unsupported integration type key
- **THEN** the worker exits at startup with a clear configuration error
