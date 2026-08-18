## Context

`WorkerConsumer.run()` uses:

```python
with client.get_queue_receiver(queue_name, max_wait_time=5) as receiver:
    for message in receiver:
        process_message(...)
```

The Azure Service Bus Python SDK documents that when `max_wait_time` is set on the receiver constructor, the streaming iterator **stops after the timeout if no messages arrive** (`_get_streaming_message_iter`). That ends `run()`, `run_worker()` returns 0, and Container Apps restart the container indefinitely.

Observed in production: ~10s start-to-exit (startup + one 5s idle wait), exit code 0, `ProcessExited`, min/max replicas 1, no scale rules.

## Goals / Non-Goals

**Goals:**

- Worker process stays alive on an idle queue until SIGTERM/interrupt or unrecoverable error.
- Per-receive poll interval remains tunable (default 5s) without affecting process lifetime.
- Clear operator docs so poll interval is not mistaken for “worker timeout.”

**Non-Goals:**

- Rewriting the consumer as async.
- Session queues or batch receive tuning.
- Workaround shell loops in the Docker entrypoint.

## Decisions

### Receive loop pattern

| Option | Verdict |
| --- | --- |
| Remove `max_wait_time` from constructor; keep `for message in receiver` | Rejected — iterator semantics remain easy to misuse; no clear per-poll interval |
| **`while True` + `receive_messages(max_message_count=1, max_wait_time=N)`** | **Chosen** — SDK documents empty list → continue; poll interval is explicit |
| `while True` + recreate receiver on error only | Deferred — add if connection drops need explicit reconnect (out of scope unless tests reveal gap) |

Implementation sketch:

```python
with client.get_queue_receiver(queue_name) as receiver, client.get_queue_sender(...) as sender:
    while True:
        for message in receiver.receive_messages(max_message_count=1, max_wait_time=poll_seconds):
            process_message(message, receiver, ...)
```

Constructor **`max_wait_time` MUST NOT be set** when using this pattern.

### Config: `serviceBus.receiveMaxWaitSeconds`

**Include in config.yaml** — yes, as an optional tuning knob under `serviceBus`:

| Field | Default | Valid range | Env override |
| --- | --- | --- | --- |
| `receiveMaxWaitSeconds` | `5` | integer ≥ 1 | `SERVICEBUS_RECEIVE_MAX_WAIT_SECONDS` |

**Rationale for config (not just a constant):**

- Matches existing operator-tunable settings (`snyk.maxConcurrentPendingImports`, `ignoredRepos.reconciliationIntervalMinutes`).
- Lets operators reduce poll frequency on very quiet queues (minor cost savings) or shorten waits in test environments.
- Documented as **per receive attempt**, not worker shutdown.

**Rationale against making it prominent:**

- Most operators should never change it; default 5 is fine.
- Keep it optional in `config.yaml.example` as a commented line only.

**Rejected:** putting poll interval only in env — inconsistent with other `serviceBus.*` settings already in YAML.

### Error handling

- Transient Service Bus errors inside the loop: log and retry with backoff (minimal: re-raise only if existing behavior already crashes; prefer small sleep + continue if integration tests show link drops).
- Startup failures (config, table ensure, auth): unchanged — exit non-zero.

### Testing

- **Unit:** mock receiver where `receive_messages` returns `[]` repeatedly; assert `run()` does not return within test timeout (or assert call count > 1).
- **Integration:** unchanged message-processing tests; no requirement for long-running integration test against real SB.

## Risks / Trade-offs

| Risk | Mitigation |
| --- | --- |
| Operator sets very large `receiveMaxWaitSeconds` | Cap at reasonable max (e.g. 300) in parser; document default |
| Operator misreads docs and expects worker to exit | CONFIGURATION.md wording: “does not stop the worker” |
| Infinite loop hides connection death | Log at DEBUG on poll cycles; revisit reconnect if reported |

## Migration Plan

1. Merge with `ignored-repos-config`; tag release **`v1.1.0`** (bundled minor release, not a standalone patch).
2. Operators redeploy Container App image to `v1.1.0` — no config change required for the receive-loop fix alone.
3. Optional: set `serviceBus.receiveMaxWaitSeconds` only if tuning desired.

## Open Questions

_None — config field name and default approved in this design._
