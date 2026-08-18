## Why

The worker Container App restart loop (~2000 restarts, exit code 0, ~10s cycle) is caused by a bug in the Service Bus receive loop: `max_wait_time=5` is passed to `get_queue_receiver()`, and the Azure SDK stops the `for message in receiver` iterator after that timeout when the queue is idle. The process exits cleanly (code 0), Azure Container Apps restarts it, and the cycle repeats. This breaks production deployments on an empty or quiet queue and is unrelated to KEDA scaling, ingress, or auth.

## What Changes

- Fix the consumer so the worker **runs continuously** when the queue is idle (no exit after a poll timeout).
- Replace `for message in receiver` + constructor `max_wait_time` with an explicit `while True` + `receive_messages(max_wait_time=…)` loop (SDK-recommended pattern for long-running consumers).
- Add optional operator tuning: `serviceBus.receiveMaxWaitSeconds` in config (default `5`), with env override `SERVICEBUS_RECEIVE_MAX_WAIT_SECONDS`.
- Add unit test asserting `WorkerConsumer.run()` does not return when no messages arrive within multiple poll intervals.
- Add README deployment troubleshooting entry for restart loops caused by process exit on idle queue.
- Release **`v1.1.0`** with `ignored-repos-config` (same deploy); operators redeploy that tag for the receive-loop fix.

## Capabilities

### New Capabilities

_None._

### Modified Capabilities

- `sync-worker`: Add requirement that the worker MUST NOT exit when the queue is idle; document receive polling interval configuration.

## Impact

- **Code:** `src/worker/consumer.py`, `src/config/settings.py`, tests under `tests/worker/` and `tests/config/`.
- **Docs:** `CONFIGURATION.md`, `data/config.yaml.example`, README troubleshooting (optional one-line in deployment section).
- **Dependencies:** none (behavior fix only; existing `azure-servicebus`).
- **Breaking:** none — default poll interval remains 5 seconds; behavior change fixes incorrect exit-on-idle.

## Non-goals

- Changing import polling, follow-up backoff, or reconciliation intervals.
- Adding HTTP health endpoints for Container Apps probes.
- KEDA / scale-rule documentation changes (ScaledObject warnings remain platform noise).
- CLI flag for receive poll interval (config/env only, matching existing settings pattern).
