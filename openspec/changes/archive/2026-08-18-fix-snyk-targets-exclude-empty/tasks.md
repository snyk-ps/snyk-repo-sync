## 1. Snyk client fix

- [x] 1.1 Add `exclude_empty=false` to `SnykClient.find_target_id` query parameters
- [x] 1.2 Unit test: assert GET `/rest/orgs/{org}/targets` request includes `exclude_empty=false`
- [x] 1.3 Unit test: mocked empty-target record is returned by `find_target_id`

## 2. Documentation

- [x] 2.1 Add brief troubleshooting note to CONFIGURATION.md: `target_resolve_failed` on empty repos after successful import (Snyk API `exclude_empty` default)

## 3. Verification

- [x] 3.1 Run unit test suite

## 4. Release

- [ ] 4.1 Tag patch release **`v1.1.1`** and redeploy Container App

## 5. Archive (human step)

- [ ] Merge `openspec/specs/` only when archiving: do **not** copy or merge `openspec/changes/fix-snyk-targets-exclude-empty/specs/*.md` into `openspec/specs/` during implementation; run `openspec archive fix-snyk-targets-exclude-empty` to fold deltas into canonical specs
