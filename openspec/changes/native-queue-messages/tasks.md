## 1. Queue message parsing

- [ ] 1.1 Replace `src/worker/envelope.py` with native queue message parser (`message.py` or equivalent)
- [ ] 1.2 ADO detection: `eventType == AzureDevOpsAuditEvent` **or** `subject == AzureDevOps/Auditing`; extract audit record from `data`
- [ ] 1.3 GitHub detection by webhook shape; rename DLQ reason `InvalidEnvelope` → `InvalidMessage`
- [ ] 1.4 Update `handler.py`, `consumer.py`, and `normalize.py` to accept audit record from parsed message (not `rawPayload`)
- [ ] 1.5 Log parsed and normalized fields in log message text (not only `logging.extra`)

## 2. Fixtures and tests

- [ ] 2.1 Add `data/fixtures/eventgrid_ado_*.json` (full Event Grid wrapper) for four lifecycle actions; use real export for default-branch fixture
- [ ] 2.2 Remove `data/fixtures/transport_envelope_*.json`; add raw GitHub webhook fixture if needed
- [ ] 2.3 Replace `tests/worker/test_envelope.py` with `test_message.py` (ADO by subject, ADO by eventType, GitHub, invalid shapes)
- [ ] 2.4 Update `test_normalize.py`, `test_consumer.py`, and integration tests for native fixtures

## 3. Documentation

- [ ] 3.1 INGESTION.md: new architecture diagram (Event Grid subscription → Service Bus); add `subject` filter; remove transport envelope section and ingress handler Step 4; update troubleshooting
- [ ] 3.2 CONFIGURATION.md: replace transport envelope with queue message shapes; update DLQ reasons
- [ ] 3.3 README.md: features and troubleshooting (remove envelope references)
- [ ] 3.4 CONTRIBUTING.md: integration test fixture wording
- [ ] 3.5 openspec/SPEC.md: update capability descriptions for `event-ingestion`, `ado-provisioning`, `github-webhook-ingestion`

## 4. Quality

- [ ] 4.1 Run unit tests; integration tests where configured
- [ ] 4.2 Snyk Code on changed worker modules

## 5. OpenSpec archive

- [ ] 5.1 Merge `openspec/specs/` only when archiving: do **not** copy or merge `openspec/changes/native-queue-messages/specs/*.md` into `openspec/specs/` during implementation; run `openspec archive native-queue-messages` after review and merge
