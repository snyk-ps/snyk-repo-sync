## 1. Dependencies and environment

- [ ] 1.1 Add `azure-servicebus` to `pyproject.toml`; run `uv lock` and Snyk Open Source scan
- [ ] 1.2 Implement env bootstrap: read `SERVICEBUS_CONNECTION_STRING` and queue name from environment; fail fast if missing
- [ ] 1.3 Document required Container App env vars in CONFIGURATION.md

## 2. Transport envelope

- [ ] 2.1 Implement `TransportEnvelope` dataclass with validation (`source`, `ingressId`, `receivedAt`, `rawPayload`) in `src/worker/envelope.py`
- [ ] 2.2 Add unit tests for valid ADO/GitHub envelopes and malformed inputs in `tests/worker/test_envelope.py`
- [ ] 2.3 Add ADO and GitHub transport envelope JSON fixtures under `data/fixtures/`

## 3. Service Bus consumer

- [ ] 3.1 Implement receive loop with complete and dead-letter handling in `src/worker/consumer.py`
- [ ] 3.2 Wire slice-1 handler: validate envelope → complete message (no normalization or sync)
- [ ] 3.3 Add unit tests for consumer handler with mocked Service Bus client in `tests/worker/test_consumer.py`

## 4. Worker entrypoint

- [ ] 4.1 Add `worker run` subcommand in `src/commands/worker.py` and wire into `src/main.py`
- [ ] 4.2 Add unit tests for CLI parser and startup validation in `tests/commands/test_worker.py`

## 5. Integration tests

- [ ] 5.1 Add integration tests that publish transport fixtures to configured/emulated queue and assert worker completes messages
- [ ] 5.2 Document how to run integration tests (env vars, emulator) in CONTRIBUTING.md or CONFIGURATION.md

## 6. Quality

- [ ] 6.1 Ensure logs omit Service Bus connection strings and other secrets
- [ ] 6.2 Run Snyk Code on new worker modules

## 7. OpenSpec archive

- [ ] 7.1 Merge `openspec/specs/` only when archiving: do **not** copy or merge `openspec/changes/add-worker-queue-consumer/specs/*.md` into `openspec/specs/` during implementation; run `openspec archive add-worker-queue-consumer` after review and merge
