## 1. Config schema and loading

- [x] 1.1 Add `ScopeMappingSettings`, `AdoScopeEntry`, `GitHubScopeEntry` dataclasses and parse `scopeMapping` from YAML in config loader
- [x] 1.2 Validate: non-empty lookup keys and `snykOrgId`, duplicate `projectName` / `orgName` detection
- [x] 1.3 Extend `WorkerSettings` (or companion type) to include optional scope mapping settings
- [x] 1.4 Unit tests in `tests/config/test_settings.py` and/or `tests/config/test_scope_mapping.py` for valid config, duplicates, defaults, empty section

## 2. Scope mapping resolver

- [x] 2.1 Implement `resolve_scope_mapping(source, lookup_key)` returning mapped / default / unmapped
- [x] 2.2 Unit tests: mapped ADO, mapped GitHub (resolver only), default fallback, unmapped

## 3. Worker integration

- [x] 3.1 Pass scope mapping settings into handler/consumer
- [x] 3.2 After ADO normalization, resolve by `ado.project_name`; log structured outcome (include `snyk_org_id` or unmapped warning)
- [x] 3.3 Update `tests/worker/test_handler.py` and consumer tests for mapped / unmapped / default paths
- [x] 3.4 Confirm GitHub path unchanged (complete without normalization)

## 4. Config example and documentation

- [x] 4.1 Update `data/config.yaml.example` with commented `scopeMapping` section
- [x] 4.2 **CONFIGURATION.md**: full `scopeMapping` schema table, example YAML, lookup key rules, unmapped/default behavior, note that integration ids are not in config
- [x] 4.3 **README.md**: feature bullet and config table row for scope mapping; adjust “deferred” language
- [x] 4.4 **CONTRIBUTING.md** / **INGESTION.md**: update any remaining “mapping deferred” references

## 5. Quality

- [x] 5.1 Run unit tests (`uv run pytest -m "not integration"`)
- [x] 5.2 Snyk Code on new/changed modules

## 6. OpenSpec archive

- [ ] 6.1 Merge `openspec/specs/` only when archiving: do **not** copy or merge `openspec/changes/scope-mapping-config/specs/*.md` into `openspec/specs/` during implementation; run `openspec archive scope-mapping-config` after review and merge
