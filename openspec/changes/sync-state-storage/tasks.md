## 1. Configuration and CLI

- [ ] 1.1 Add unified config loader: parse YAML from `--config` (default `data/config.yaml`); fail fast if file missing or invalid
- [ ] 1.2 Merge config with env overrides (`SERVICEBUS_FULLY_QUALIFIED_NAMESPACE`, `SERVICEBUS_QUEUE_NAME`, `SYNC_STATE_STORAGE_ACCOUNT_ENDPOINT`, `SYNC_STATE_TABLE_NAME`); env takes precedence
- [ ] 1.3 Add `--config` argument to `worker run`; remove `src/config/service_bus.py` connection-string env loader
- [ ] 1.4 Add `data/config.yaml.example` documenting `serviceBus` and `syncState` sections

## 2. Azure identity and Service Bus

- [ ] 2.1 Add `azure-identity`, `azure-data-tables`, and `pyyaml` dependencies; run Snyk Open Source scan
- [ ] 2.2 Refactor `WorkerConsumer` to use `ServiceBusClient(fqn, credential=DefaultAzureCredential())`; remove `from_connection_string`
- [ ] 2.3 Update `tests/config/` and `tests/worker/test_consumer.py` for new config model
- [ ] 2.4 Update integration tests to use config file + `DefaultAzureCredential` (document `az login` prerequisite)

## 3. Sync state module

- [ ] 3.1 Implement `src/sync_state/` table client: `DefaultAzureCredential`, `create_table_if_not_exists`, get entity by partition/row key
- [ ] 3.2 Implement `_meta` and repository entity models matching canonical schema
- [ ] 3.3 Unit tests for config resolution, entity serialization, and table client (mocked SDK)

## 4. Worker integration

- [ ] 4.1 Startup sequence: load config → init Table client → ensure table → start Service Bus consumer
- [ ] 4.2 After ADO normalization, load `_meta`; DLQ with reason `UnknownScope` + alert when missing or `enabled: false`
- [ ] 4.3 Update handler/consumer tests for slice-3 _meta lookup path
- [ ] 4.4 Add `UNKNOWN_SCOPE_REASON` constant and wire dead-letter in consumer

## 5. Docker and local dev

- [ ] 5.1 Update Dockerfile: `ENTRYPOINT ["python", "src/main.py"]`, `CMD ["worker", "run", "--config", "/config/config.yaml"]`
- [ ] 5.2 Update `.vscode/launch.json` to pass `--config data/config.yaml` (optional; default already sufficient)

## 6. Documentation

- [ ] 6.1 CONFIGURATION.md: config schema, env override table, RBAC checklist, table entity schema; remove all connection-string references
- [ ] 6.2 README.md: managed identity, config file mount, RBAC roles, troubleshooting (unknown scope DLQ)
- [ ] 6.3 INGESTION.md: update worker prerequisites table (config + RBAC, not connection string)
- [ ] 6.4 CONTRIBUTING.md: local dev setup (`data/config.yaml` + `az login`); update integration test instructions
- [ ] 6.5 Remove `SERVICEBUS_CONNECTION_STRING` from `.env.example` and any remaining docs/examples

## 7. Quality

- [ ] 7.1 Run unit tests; integration tests where Azure credentials and config are available
- [ ] 7.2 Snyk Code on new and changed modules

## 8. OpenSpec archive

- [ ] 8.1 Merge `openspec/specs/` only when archiving: do **not** copy or merge `openspec/changes/sync-state-storage/specs/*.md` into `openspec/specs/` during implementation; run `openspec archive sync-state-storage` after review and merge
