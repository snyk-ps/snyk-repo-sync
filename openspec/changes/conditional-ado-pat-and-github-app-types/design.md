## Context

Worker startup currently parses `ado.organization`, requires `ADO_PAT`, and constructs `AdoClient` unconditionally. The client has one responsibility: resolving an ADO repository's default branch when neither an event nor sync state provides one. GitHub events never use it.

Scope-mapping section keys also serve directly as Snyk integration types. They are matched against `GET /v1/org/{org_id}/integrations` results and passed as `source_types` to `GET /rest/orgs/{org_id}/targets`. The current `github-cloud` and `github-server` keys therefore propagate invalid type values into both paths; Snyk uses `github-cloud-app` and `github-server-app`.

## Goals / Non-Goals

**Goals:**

- Let deployments without explicit `scopeMapping.azure-repos` entries start without `ado.organization` or `ADO_PAT`.
- Preserve authenticated ADO default-branch enrichment whenever `azure-repos` mappings are configured.
- Fail an unexpected ADO enrichment attempt clearly when the deployment has no ADO client, without guessing a branch.
- Align accepted GitHub App mapping keys with Snyk integration and target source type values.
- Keep configuration, runtime types, tests, canonical documentation, and deployment examples consistent.

**Non-Goals:**

- Add GitHub API enrichment for missing default branches.
- Replace the ADO PAT with managed identity or another ADO authentication mechanism.
- Change the Snyk integration-list, import, import-status, or target-list endpoints.
- Provide compatibility aliases for `github-cloud` or `github-server`.
- Change how `defaultSnykOrgId` routes otherwise unmapped events.

## Decisions

### Use configured ADO mappings as the startup requirement signal

After parsing `scopeMapping`, settings loading will parse and require ADO organization settings only when `ado_by_project_name` is non-empty. Worker startup will likewise require `ADO_PAT` and construct `AdoClient` only in that case.

This makes the requirement depend on the operator's explicit `azure-repos` intent rather than the event transport, which can carry both providers. An empty or absent `azure-repos` list is treated as no configured ADO integration.

Alternative considered: require ADO credentials whenever `defaultSnykOrgId` exists because it can route ADO events. This would continue blocking GitHub-only deployments that use the default mapping, contrary to the requested configuration boundary.

### Represent the ADO dependency as optional

`WorkerSettings.ado` and the lifecycle ADO client dependency will be optional. Branch resolution will continue to prefer event and sync-state values. Only an ADO event lacking both values needs the client; if none was configured, resolution will raise a clear configuration error and the consumer will dead-letter that message as `ConfigurationError` so the worker continues processing other messages.

Alternative considered: construct a placeholder client with empty credentials. That defers the error to an outbound request and produces a misleading authentication failure.

### Reject obsolete GitHub keys

The accepted GitHub set will be `github`, `github-cloud-app`, `github-server-app`, and `github-enterprise`. The corrected section key remains the single value used for integration lookup and target `source_types` filtering.

Alternative considered: accept old names as aliases and translate them. Aliases would hide invalid Snyk terminology, complicate default type selection, and leave ambiguous operator configuration; the proposal intentionally treats this as a breaking correction.

### Keep endpoint behavior unchanged

The corrected type selects an integration id from `GET /v1/org/{org_id}/integrations`. Import continues through `POST /v1/org/{org_id}/integrations/{integration_id}/import`, and target lookup continues through `GET /rest/orgs/{org_id}/targets` with the corrected type in `source_types`.

## Risks / Trade-offs

- **[Unexpected ADO event in a GitHub-only deployment]** → Events that already contain a branch can still proceed through the default mapping; an event needing enrichment fails with an explicit missing-ADO-configuration error.
- **[Existing operators use obsolete GitHub keys]** → Startup validation rejects them and names the corrected allowed keys; release notes and configuration docs call out the migration.
- **[Optional dependency propagates through lifecycle code]** → Keep optional handling at branch resolution and test both branch-present and enrichment-required paths to avoid unrelated `None` checks.
- **[Docs continue implying the PAT is universal]** → Update the README deployment secret tables, configuration reference, and example comments together.

## Migration Plan

1. Before deploying, rename `scopeMapping.github-cloud` to `scopeMapping.github-cloud-app` and `scopeMapping.github-server` to `scopeMapping.github-server-app`.
2. Deploy the updated worker. Existing `github` and `github-enterprise` configuration requires no migration.
3. For deployments with one or more `azure-repos` entries, continue supplying `ado.organization` and `ADO_PAT` with Code (Read).
4. For deployments without `azure-repos` entries, remove those ADO settings and secrets if they are otherwise unused.
5. Roll back by restoring the prior worker and prior GitHub section names; restore ADO settings and `ADO_PAT` because the prior worker requires them unconditionally.

## Open Questions

_None._
