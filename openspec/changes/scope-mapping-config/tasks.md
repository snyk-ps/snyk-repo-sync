## 1. Config schema and loading

- [ ] 1.1 Add `ScopeMappingSettings`, `AdoScopeEntry`, `GitHubScopeEntry` dataclasses and parse `scopeMapping` from YAML in config loader
- [ ] 1.2 Validate: non-empty lookup keys and `snykOrgId`, duplicate `projectName` / `orgName` detection, `exclusionGlobs` list shape
- [ ] 1.3 Extend `WorkerSettings` (or companion type) to include optional scope mapping settings
- [ ] 1.4 Unit tests in `tests/config/test_settings.py` and/or `tests/config/test_scope_mapping.py` for valid config, duplicates, defaults, empty section

## 2. Scope mapping resolver

- [ ] 2.1 Implement `resolve_scope_mapping(source, lookup_key)` returning mapped / default / unmapped
- [ ] 2.2 Unit tests: mapped ADO, mapped GitHub (resolver only), default fallback, unmapped, exclusion globs passthrough

## 3. Worker integration

- [ ] 3.1 Pass scope mapping settings into handler/consumer
- [ ] 3.2 After ADO normalization, resolve by `ado.project_name`; log structured outcome (include `snyk_org_id` or unmapped warning)
- [ ] 3.3 Update `tests/worker/test_handler.py` and consumer tests for mapped / unmapped / default paths
- [ ] 3.4 Confirm GitHub path unchanged (complete without normalization)

## 4. Config example and documentation

- [ ] 4.1 Update `data/config.yaml.example` with commented `scopeMapping` section
- [ ] 4.2 **CONFIGURATION.md**: full `scopeMapping` schema table, example YAML, lookup key rules, unmapped/default behavior, note that integration ids are not in config
- [ ] 4.3 **README.md**: feature bullet and config table row for scope mapping; adjust “deferred” language
- [ ] 4.4 **CONTRIBUTING.md** / **INGESTION.md**: update any remaining “mapping deferred” references

## 5. Quality

- [ ] 5.1 Run unit tests (`uv run pytest -m "not integration"`)
- [ ] 5.2 Snyk Code on new/changed modules

## 6. OpenSpec archive

- [ ] 6.1 Merge `openspec/specs/` only when archiving: do **not** copy or merge `openspec/changes/scope-mapping-config/specs/*.md` into `openspec/specs/` during implementation; run `openspec archive scope-mapping-config` after review and merge
