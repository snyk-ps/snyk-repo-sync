## 1. Normalized model

- [x] 1.1 Add `NormalizedEvent`, `AdoScope`, and payload types in `src/worker/normalize.py`
- [x] 1.2 Implement `strip_branch_ref()` and ADO audit field mapping for four `ActionId` values
- [x] 1.3 Add `NormalizationError` and map to dead-letter reason `InvalidNormalization`

## 2. Worker wiring

- [x] 2.1 Update message handler to call ADO normalization after envelope validation
- [x] 2.2 Log normalized fields (`event_type`, `scope_id`, `repository_id`, `event_id`, ADO org/project) without secrets
- [x] 2.3 Pass-through GitHub envelopes with deferred-normalization log; complete without side effects

## 3. Fixtures and tests

- [x] 3.1 Update `data/fixtures/transport_envelope_ado.json` with org scope fields from real audit export
- [x] 3.2 Add ADO transport fixtures for create, rename, and delete audit actions
- [x] 3.3 Add unit tests in `tests/worker/test_normalize.py` for all four ADO actions, branch ref stripping, missing fields, and unsupported `ActionId`
- [x] 3.4 Update consumer/handler tests for slice-2 behavior
- [x] 3.5 Keep integration tests passing (ADO fixture completes end-to-end)

## 4. Documentation

- [x] 4.1 Document normalized event schema (org, project, repo, branch) in `CONFIGURATION.md`
- [x] 4.2 Update `README.md` slice description (ADO normalization; sync deferred)
- [x] 4.3 Extend `INGESTION.md` audit-fields table with `ScopeId`, `ScopeDisplayName`, and normalized mapping

## 5. Quality

- [x] 5.1 Run unit tests and integration tests (where configured)
- [x] 5.2 Run Snyk Code on new normalization modules

## 6. OpenSpec archive

- [ ] 6.1 Merge `openspec/specs/` only when archiving: do **not** copy or merge `openspec/changes/ado-lifecycle-normalization/specs/*.md` into `openspec/specs/` during implementation; run `openspec archive ado-lifecycle-normalization` after review and merge
