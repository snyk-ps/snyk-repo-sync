## 1. Transport configuration

- [x] 1.1 Add `messaging.transport` (`serviceBus` default, `kafka`) with env override `MESSAGING_TRANSPORT`; require `serviceBus` settings only for `serviceBus`, and `storageQueue.queueName` only for `kafka`
- [x] 1.2 Derive the queue service URL from `syncState.storageAccountEndpoint` by replacing the `.table.` host label with `.queue.`; fail startup when that label is missing
- [x] 1.3 Parse `storageQueue` poison queue name (default `{queueName}-poison`), visibility timeout (default 60), and receive wait (default 5, bounds 1–300), plus env overrides; reject invalid queue names
- [x] 1.4 Unit tests for default transport, env precedence, URL derivation, and invalid names

## 2. Follow-up transport interface

- [x] 2.1 Introduce a follow-up transport interface (receive, complete, dead-letter, delayed send) and move the current Service Bus receive loop behind it without changing `serviceBus` behavior
- [x] 2.2 Add a `GitHubEventSource` protocol and no HTTP implementation
- [x] 2.3 `worker run` with `messaging.transport: kafka` exits non-zero with a clear error that the event-connector REST contract is pending, and does not construct a Service Bus client or fall back

## 3. Storage queue follow-ups

- [x] 3.1 Add `azure-storage-queue` with `uv lock`; run a Snyk Open Source scan and do not keep the dependency if it introduces high or critical issues
- [x] 3.2 Implement the storage-queue transport with `DefaultAzureCredential`: delayed send via initial visibility timeout, delete on success, poison-queue copy plus source delete on dead-letter, and `MaxDequeueCountExceeded` at dequeue count 10
- [x] 3.3 Reject storage-queue bodies that lack a supported `syncPhase` with reason `InvalidMessage`; keep follow-up JSON identical to the Service Bus body
- [x] 3.4 Unit tests with a fake queue client for delay, delete, poison settlement, dequeue-count exhaustion, invalid bodies, and idle polling that does not exit

## 4. Documentation

- [x] 4.1 Update `CONFIGURATION.md` with `messaging.transport`, `storageQueue` keys, env overrides, and same-account queue derivation
- [x] 4.2 Update `INGESTION.md` and `README.md`: Service Bus path unchanged; Kafka path is consumption-only and not runnable until the REST spec exists; storage queue and poison queue are pre-provisioned in the sync-state account; queue data role; no KEDA guidance for the storage queue

## 5. Archive

- [ ] 5.1 Merge `openspec/specs/` only when archiving: do **not** copy or merge `openspec/changes/github-kafka-storage-queue/specs/*.md` into `openspec/specs/` during implementation; run `openspec archive github-kafka-storage-queue` (or project equivalent) to fold deltas into canonical specs
