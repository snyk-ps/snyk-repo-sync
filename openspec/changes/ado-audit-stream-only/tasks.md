## 1. Operator documentation and diagrams

- [x] 1.1 Replace `INGESTION.md` mermaid diagram with audit-only ADO architecture (GitHub path unchanged)
- [x] 1.2 Add latency note (~30 min batch delay) to `INGESTION.md` Architecture and Troubleshooting sections
- [x] 1.3 Rewrite `INGESTION.md`: remove service hook sections; single ADO audit-stream setup with four-ActionId Event Grid filter
- [x] 1.4 Update `README.md`: remove ADO service hook mentions; link operators to audit-only ingress in INGESTION.md
- [x] 1.5 Update `CONFIGURATION.md`: remove service hook references in ingress setup links and text
- [x] 1.6 Update `openspec/SPEC.md` capability descriptions for `ado-provisioning` and `event-ingestion`

## 2. Fixtures and tests

- [x] 2.1 Replace `data/fixtures/transport_envelope_ado.json` with audit-record `rawPayload` (e.g. `Git.RepositoryDefaultBranchChanged`)
- [x] 2.2 Update `tests/worker/test_envelope.py` assertions for audit-shaped `rawPayload`
- [x] 2.3 Update `tests/worker/test_consumer.py` inline body to use audit `ActionId` instead of `git.repo.created`
- [x] 2.4 Verify `tests/integration/test_worker_service_bus.py` passes with updated ADO fixture

## 3. Verification

- [x] 3.1 Run `uv run pytest -m "not integration"`
- [x] 3.2 Grep repo for remaining ADO service hook references (`service hook`, `git.repo.`, `ado-hook`) and remove stragglers in scope

## 4. OpenSpec archive

- [ ] 4.1 Merge `openspec/specs/` only when archiving: do **not** copy or merge `openspec/changes/ado-audit-stream-only/specs/*.md` into `openspec/specs/` during implementation; run `openspec archive ado-audit-stream-only` after review and merge
