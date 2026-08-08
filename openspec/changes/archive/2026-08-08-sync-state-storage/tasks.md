## 1. Configuration and CLI

- [x] 1.1 Add unified config loader: parse YAML from `--config` (default `data/config.yaml`); fail fast if file missing or invalid
- [x] 1.2 Merge config with env overrides (`SERVICEBUS_FULLY_QUALIFIED_NAMESPACE`, `SERVICEBUS_QUEUE_NAME`, `SYNC_STATE_STORAGE_ACCOUNT_ENDPOINT`, `SYNC_STATE_TABLE_NAME`); env takes precedence
- [x] 1.3 Add `--config` argument to `worker run`; remove `src/config/service_bus.py` connection-string env loader
- [x] 1.4 Add `data/config.yaml.example` documenting `serviceBus` and `syncState` sections

## 2. Azure identity and Service Bus

- [x] 2.1 Add `azure-identity`, `azure-data-tables`, and `pyyaml` dependencies; run Snyk Open Source scan
- [x] 2.2 Refactor `WorkerConsumer` to use `ServiceBusClient(fqn, credential=DefaultAzureCredential())`; remove `from_connection_string`
- [x] 2.3 Update `tests/config/` and `tests/worker/test_consumer.py` for new config model
- [x] 2.4 Update integration tests to use config file + `DefaultAzureCredential` (document `az login` prerequisite)

## 3. Sync state module

- [x] 3.1 Implement `src/sync_state/` table client: `DefaultAzureCredential`, `create_table_if_not_exists`, get entity by partition/row key
- [x] 3.2 Implement repository entity model matching canonical schema (no `_meta` rows)
- [x] 3.3 Unit tests for config resolution, entity serialization, and table client (mocked SDK)

## 4. Worker integration

- [x] 4.1 Startup sequence: load config → init Table client → ensure table → start Service Bus consumer
- [x] 4.2 After ADO normalization, log normalized event and complete message (no scope mapping or repository state access)
- [x] 4.3 Update handler/consumer tests for slice-3 normalize-and-complete path
- [x] 4.4 Remove `_meta` lookup, `UnknownScope` DLQ, and `src/worker/scope.py`

## 5. Docker and local dev

- [x] 5.1 Update Dockerfile: `ENTRYPOINT ["python", "src/main.py"]`, `CMD ["worker", "run", "--config", "/config/config.yaml"]`
- [x] 5.2 Update `.vscode/launch.json` to pass `--config data/config.yaml` (optional; default already sufficient)

## 6. Documentation

- [x] 6.1 CONFIGURATION.md: config schema, env override table, RBAC checklist, table entity schema; remove all connection-string references
- [x] 6.2 README.md: managed identity, config file mount, RBAC roles; remove `_meta` / `UnknownScope` troubleshooting
- [x] 6.6 Add `openspec/specs/scope-mapping/spec.md` (implementation deferred to next change)
- [x] 6.3 INGESTION.md: update worker prerequisites table (config + RBAC, not connection string)
- [x] 6.4 CONTRIBUTING.md: local dev setup (`data/config.yaml` + `az login`); update integration test instructions
- [x] 6.5 Remove `SERVICEBUS_CONNECTION_STRING` from `.env.example` and any remaining docs/examples

## 7. Quality

- [x] 7.1 Run unit tests; integration tests where Azure credentials and config are available
- [x] 7.2 Snyk Code on new and changed modules

## 8. OpenSpec archive

- [x] 8.1 Merge `openspec/specs/` only when archiving: do **not** copy or merge `openspec/changes/sync-state-storage/specs/*.md` into `openspec/specs/` during implementation; run `openspec archive sync-state-storage` after review and merge
