## 1. Config and parsing

- [ ] 1.1 Add `ignoredRepos.path` and optional `ignoredRepos.reconciliationIntervalMinutes` (default 15) to settings loader; resolve relative paths from config directory
- [ ] 1.2 Implement `src/config/ignored_repos.py`: load UTF-8 YAML/JSON, validate schema, compile regex patterns, `is_ignored()` matcher
- [ ] 1.3 Add `snyk.targetRemoval.onIgnore` to `snyk_settings.py` (default `deactivate`)
- [ ] 1.4 Unit tests: valid/invalid files, both formats, filter types, required `source`, duplicate repos, bad regex

## 2. Sync state and policy persistence

- [ ] 2.1 Persist loaded ignore policy to sync-state meta row on successful load
- [ ] 2.2 Load persisted policy when file reload fails during reconciliation
- [ ] 2.3 Unit tests: policy round-trip and fallback to last persisted policy

## 3. Worker integration

- [ ] 3.1 Load ignore policy at worker startup when `ignoredRepos.path` is configured; fail fast if file missing
- [ ] 3.2 Wire ignore check into lifecycle handler after scope mapping: skip import on match; remove active target per `onIgnore`
- [ ] 3.3 Handle rename-into-ignore and default-branch-change-on-ignored-repo at event time
- [ ] 3.4 Unit tests: worker skips import; rename into ignore removes target without import

## 4. Background reconciliation

- [ ] 4.1 Implement reconciliation loop in worker process (default 15-minute interval)
- [ ] 4.2 Scan active repository rows; remove targets matching policy per `onIgnore`; update sync state
- [ ] 4.3 Structured logging: match reason (explicit entry or pattern group `id`), reload failures
- [ ] 4.4 Unit/integration tests: retroactive ignore entry deactivates stale target

## 5. Examples and documentation

- [ ] 5.1 Add `data/ignored-repos.yaml` and `data/ignored-repos.json` examples
- [ ] 5.2 Update `data/config.yaml.example` with `ignoredRepos` and `onIgnore` comments
- [ ] 5.3 Update **CONFIGURATION.md**: ignore policy schema, `onIgnore`, Azure Files upload step
- [ ] 5.4 Update **README.md** config mount section to mention ignore policy file
- [ ] 5.5 Update **data/DESIGN.md**: ignore policy section, supported actions table, infrastructure table, key configuration

## 6. Archive (human step)

- [ ] Merge `openspec/specs/` only when archiving: do **not** copy or merge `openspec/changes/ignored-repos-config/specs/*.md` into `openspec/specs/` during implementation; run `openspec archive ignored-repos-config` to fold deltas into canonical specs
