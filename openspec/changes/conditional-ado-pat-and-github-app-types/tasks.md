## 1. Scope Mapping Types

- [x] 1.1 Replace `github-cloud` and `github-server` in the scope-mapping type definitions and allow-list with `github-cloud-app` and `github-server-app`, retaining `github` and `github-enterprise`.
- [x] 1.2 Update scope-mapping parser and resolution unit tests for both App types, obsolete-key rejection, default integration selection, and corrected validation messages.

## 2. Conditional ADO Configuration

- [x] 2.1 Parse scope mapping before ADO settings and make `WorkerSettings.ado` absent when no `azure-repos` mappings are configured.
- [x] 2.2 Require `ado.organization` and `ADO_PAT` and construct `AdoClient` only when at least one `azure-repos` mapping is configured.
- [x] 2.3 Make the lifecycle ADO dependency optional and dead-letter with a clear configuration error only when an ADO event without an event or sync-state branch requires enrichment but no client is configured.
- [x] 2.4 Add or update unit tests for GitHub-only startup without ADO settings, mapped ADO startup requirements, branch-present ADO processing without enrichment, and missing-client enrichment failure.

## 3. Snyk Integration and Target Behavior

- [x] 3.1 Update integration resolver, lifecycle, and client-facing test fixtures to use `github-cloud-app` and `github-server-app`.
- [x] 3.2 Verify tests assert corrected App types are matched from `GET /v1/org/{org_id}/integrations` results and passed as `source_types` to target lookup while import continues to use the resolved integration id.

## 4. Operator Documentation

- [x] 4.1 Update `CONFIGURATION.md` with the corrected GitHub App keys, their Snyk endpoint usage, and conditional `ado.organization` and `ADO_PAT` requirements.
- [x] 4.2 Update `README.md` deployment secret guidance so `ADO_PAT` is required only for configurations with `azure-repos` mappings.
- [x] 4.3 Update `data/config.yaml.example` comments and examples to show the conditional ADO settings and corrected GitHub App integration keys.

## 5. Verification

- [x] 5.1 Run repository formatting, linting, type-checking, and unit tests, fixing regressions introduced by this change.
- [x] 5.2 Run Snyk Code and confirm the implementation introduces no high-severity vulnerabilities.
- [x] 5.3 Validate the active OpenSpec change and confirm every scenario has test or documentation evidence.

## 6. Archive

- [ ] 6.1 Merge `openspec/specs/` only when archiving: do not copy or merge `openspec/changes/conditional-ado-pat-and-github-app-types/specs/*.md` into `openspec/specs/` during implementation; run `openspec archive conditional-ado-pat-and-github-app-types` (or project equivalent) to fold deltas into canonical specs.
