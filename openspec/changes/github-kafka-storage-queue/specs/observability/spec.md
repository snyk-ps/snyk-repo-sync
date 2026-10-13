## MODIFIED Requirements

### Requirement: DLQ alerting via Dynatrace
When messages are dead-lettered or unrecoverable failures occur, the system MUST raise alerts in Dynatrace (not App Insights action groups in v1).

On the Service Bus path, dead-letter means the Service Bus dead-letter queue. On the Kafka path, dead-letter means the storage poison queue defined by the `storage-queue-transport` capability. Both MUST emit a structured error log that includes the dead-letter reason. The poison-queue path MUST be alertable the same way as Service Bus dead-letter.

#### Scenario: Unmapped scope
- **WHEN** a message is processed for a scope with no entry in scope mapping config
- **THEN** Dynatrace receives a log or alert suitable for operator response per the `scope-mapping` capability

#### Scenario: Storage queue message poison-settled
- **WHEN** the worker poison-settles a storage-queue message with a dead-letter reason
- **THEN** a structured error log includes that reason and is suitable for the same Dynatrace alert class as a Service Bus dead-letter
