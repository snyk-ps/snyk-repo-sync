## Why

GitHub-only deployments currently cannot start without Azure DevOps configuration and an `ADO_PAT`, even though the PAT is used only to resolve missing default branches for ADO imports. The GitHub scope-mapping allow-list also uses `github-cloud` and `github-server`, while Snyk identifies the corresponding App integrations and targets as `github-cloud-app` and `github-server-app`.

## What Changes

- Require `ado.organization` and `ADO_PAT` at worker startup only when `scopeMapping.azure-repos` contains at least one mapping.
- Allow a worker with no ADO mappings to start without constructing an ADO API client; if such a worker unexpectedly receives an ADO event that needs default-branch enrichment, fail that message with a clear configuration error rather than guessing a branch.
- **BREAKING** Replace unsupported scope-mapping keys `github-cloud` and `github-server` with the Snyk integration types `github-cloud-app` and `github-server-app`; no aliases for the old keys are retained.
- Continue supporting `github` and `github-enterprise`.
- Use the corrected GitHub App type consistently for Snyk integration lookup and REST target `source_types` filtering.
- Update deployment and configuration documentation to describe when ADO settings and credentials are required.

## Capabilities

### New Capabilities

_None._

### Modified Capabilities

- `ado-provisioning`: Make ADO organization settings and PAT requirements conditional on configured `azure-repos` mappings while preserving branch enrichment requirements for ADO imports.
- `scope-mapping`: Replace invalid GitHub Cloud and Server section keys with the Snyk GitHub App integration type names.
- `snyk-target-sync`: Use `github-cloud-app` and `github-server-app` for integration resolution and target source filtering.
- `sync-worker`: Document and enforce conditional ADO configuration and secret injection for GitHub-only deployments.

## Impact

- **Configuration:** `scopeMapping.github-cloud` and `scopeMapping.github-server` become invalid; operators must use `github-cloud-app` and `github-server-app`.
- **Code:** Worker settings, startup dependency construction, ADO branch resolution, scope-mapping type definitions and validation, and related tests.
- **Snyk APIs:** Existing integration-list, import, and target-list endpoints remain unchanged; corrected type values flow through integration matching and `source_types`.
- **Documentation:** `README.md`, `CONFIGURATION.md`, and `data/config.yaml.example`.
- **Dependencies:** No new runtime dependencies.
