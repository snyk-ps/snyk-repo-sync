## MODIFIED Requirements

### Requirement: Config-based scope to Snyk org mapping
Operators MUST declare scope-to-Snyk-org mappings in operator config (`config.yaml`). ADO mappings MUST use ADO project name as the lookup key. GitHub mappings MUST use GitHub organization name (login) as the lookup key.

The worker MUST load and validate scope mapping entries at startup. Each mapping entry MUST include a non-empty `snykOrgId`. Duplicate lookup keys within a source MUST cause startup failure.

#### Scenario: Mapped ADO project
- **WHEN** the worker processes an ADO event for a project name present in config
- **THEN** it resolves the target Snyk organization id from config

#### Scenario: Mapped GitHub org
- **WHEN** the worker processes a GitHub event for an org name present in config
- **THEN** it resolves the target Snyk organization id from config

#### Scenario: Invalid duplicate ADO project name
- **WHEN** operator config contains two `scopeMapping.ado` entries with the same `projectName`
- **THEN** the worker exits at startup with a clear configuration error

### Requirement: Unmapped scope handling
When no config mapping exists for a scope name, the worker MUST log the failure. Configuration MAY specify an optional default Snyk organization id for unmapped scopes.

Unmapped scopes MUST NOT dead-letter the message in this implementation slice.

#### Scenario: Unmapped ADO project without default
- **WHEN** an ADO event arrives for a project name with no config mapping and no default org is configured
- **THEN** the worker logs the unmapped scope and does not perform Snyk side effects

#### Scenario: Unmapped scope with default org
- **WHEN** an ADO or GitHub event arrives for an unmapped scope name and `defaultSnykOrgId` is configured
- **THEN** the worker uses the default Snyk organization for downstream Snyk actions

### Requirement: Exclusion globs from scope mapping config
Import exclusion globs for a scope MUST be sourced from operator config as part of scope mapping. `.snyk` file exclusions MUST NOT be used for this orchestration layer.

Resolved mappings MUST expose `exclusionGlobs` from the matching config entry (empty list when unset).

#### Scenario: Import with configured exclusions
- **WHEN** a mapped repository is imported
- **THEN** the import request includes `exclusionGlobs` from the scope mapping config entry

## REMOVED Requirements

### Requirement: Deferred scope mapping implementation
**Reason**: Config-based scope → Snyk org resolution and unmapped-scope logging are implemented in this change.
**Migration**: Worker resolves scope mappings from operator config; Snyk API integration lookup remains specified but is implemented in the next change.
