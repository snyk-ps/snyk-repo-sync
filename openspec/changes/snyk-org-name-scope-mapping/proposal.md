## Why

Static `orgName`, `projectName`, and `propertyValue` rows cannot cover every Snyk organization an operator wants to target. A lookup string such as `Systèmes Centraux` should be able to select the Snyk org named `Systemes Centraux` without a config row per name, and a repository that already resolved should keep that org id for later events.

## What Changes

- Allow each integration section (`azure-repos`, `github`, `github-cloud-app`, `github-server-app`, `github-enterprise`) to enable Snyk org-name matching with explicit `enabled` and `normalize` booleans. A bare list of static rows stays valid and leaves name match off.
- When `enabled` is true, compare the existing candidate string to org names from `GET /v1/group/{groupId}/orgs`. `normalize: true` strips accents and ignores case. `normalize: false` is exact equality. Require `scopeMapping.snykGroupId` when any section enables name match.
- Resolve in order and stop at the first success: static row, org-name match, `snykOrgId` stored on the repository sync-state row, then `defaultSnykOrgId` when that value is set. A group API error retries the message and does not continue. Two or more matching org names stop with no Snyk side effects.
- Persist the resolved `snykOrgId` and `snykIntegrationType` on the repository sync-state row, and overwrite them when a later event resolves to a different org. Mapping rules stay in operator config.
- Update `CONFIGURATION.md`, `data/config.yaml.example`, the scope-mapping troubleshooting row in `README.md`, and the org-selection sentence in `INGESTION.md`.

## Capabilities

### New Capabilities

_None._

### Modified Capabilities

- `scope-mapping`: Per-section org-name match, group org listing, normalization, and the resolution order above. Static rows and the rule that an extracted value does not consult `orgName` or `projectName` stay in place.
- `sync-state`: Repository rows store the resolved Snyk org id and integration type for later resolution. Existing rows without those properties miss that step.
- `observability`: Info log for a unique org-name match. Warning log when more than one org name matches. Default and unmapped warning markers stay as they are.

## Impact

- **Code:** Scope-mapping parse and resolution, Snyk group org listing and process-local cache, repository sync-state read/write, and scope-resolution logging.
- **Configuration:** Optional object form for an integration section (`entries` plus `matchSnykOrgName.enabled` and `matchSnykOrgName.normalize`) and optional `scopeMapping.snykGroupId`. Existing list sections stay valid.
- **API:** `GET /v1/group/{groupId}/orgs` using the existing `SNYK_TOKEN`. The token must be allowed to list organizations in that group.
- **Documentation:** `CONFIGURATION.md`, `README.md`, `INGESTION.md`, and `data/config.yaml.example`.
- **Dependencies:** None.
