## ADDED Requirements

### Requirement: Continuous queue consumption on idle queue
The worker MUST remain running and continue polling the configured Service Bus queue when no messages are available. An idle queue MUST NOT cause the worker process to exit with status 0.

#### Scenario: Empty queue does not stop worker
- **WHEN** the worker starts successfully and the queue has no available messages for longer than one receive poll interval
- **THEN** the worker continues polling and does not exit solely due to the idle period

#### Scenario: Message processed after idle period
- **WHEN** the worker is polling an idle queue and a message is later published
- **THEN** the worker receives and processes the message without requiring a process restart

### Requirement: Service Bus receive poll interval
The worker MUST poll the queue using a configurable maximum wait time per receive attempt. The default MUST be 5 seconds. The setting MUST be read from `serviceBus.receiveMaxWaitSeconds` in operator config, with environment override `SERVICEBUS_RECEIVE_MAX_WAIT_SECONDS`. Invalid values MUST fail at startup with a clear configuration error.

The receive poll interval MUST NOT be implemented by setting `max_wait_time` on the Service Bus receiver constructor when iterating messages, because that causes the SDK iterator to terminate after an idle timeout.

#### Scenario: Default poll interval
- **WHEN** `serviceBus.receiveMaxWaitSeconds` is omitted from config
- **THEN** the worker uses a 5-second maximum wait per receive attempt

#### Scenario: Configured poll interval
- **WHEN** `serviceBus.receiveMaxWaitSeconds` is set to a positive integer in config
- **THEN** the worker uses that value for each receive attempt

#### Scenario: Environment override
- **WHEN** `SERVICEBUS_RECEIVE_MAX_WAIT_SECONDS` is set in the environment
- **THEN** it takes precedence over the config file value
