## 1. Config

- [ ] 1.1 Extend `ServiceBusSettings` with `receive_max_wait_seconds` (default 5); parse `serviceBus.receiveMaxWaitSeconds` and env `SERVICEBUS_RECEIVE_MAX_WAIT_SECONDS`; validate integer ≥ 1 (and optional upper cap, e.g. 300)
- [ ] 1.2 Unit tests: default, config value, env override, invalid values

## 2. Consumer fix

- [ ] 2.1 Refactor `WorkerConsumer.run()` to use `while True` + `receive_messages(max_message_count=1, max_wait_time=…)`; do **not** pass `max_wait_time` to `get_queue_receiver()`
- [ ] 2.2 Wire poll interval from `WorkerSettings.service_bus`
- [ ] 2.3 Unit test: mocked receiver returns empty list repeatedly; assert `run()` does not return (use timeout / call-count assertion)

## 3. Documentation

- [ ] 3.1 Update `CONFIGURATION.md`: document `serviceBus.receiveMaxWaitSeconds` and env override; clarify it is per-poll wait, not worker shutdown
- [ ] 3.2 Add commented example to `data/config.yaml.example`
- [ ] 3.3 Add README troubleshooting row: restart loop / exit code 0 on idle queue → upgrade to `v1.1.0` or later

## 4. Release

- [ ] 4.1 Verify full unit test suite passes
- [ ] 4.2 Ship in **`v1.1.0`** with `ignored-repos-config` (coordinate with CONTRIBUTING release process; not a standalone patch)

## 5. Archive (human step)

- [ ] Merge `openspec/specs/` only when archiving: do **not** copy or merge `openspec/changes/fix-worker-receive-loop/specs/*.md` into `openspec/specs/` during implementation; run `openspec archive fix-worker-receive-loop` to fold deltas into canonical specs
