## ADDED Requirements

### Requirement: Environment-driven worker startup
The worker MUST read Service Bus connection settings from environment variables injected by the Container App. It MUST NOT require a configuration file. It MUST fail fast at startup when required environment variables are missing.

#### Scenario: Worker starts with valid environment
- **WHEN** the worker container starts with Service Bus connection settings in the environment
- **THEN** it connects to the configured queue and begins receiving messages

#### Scenario: Missing Service Bus environment
- **WHEN** a required Service Bus environment variable is not set at startup
- **THEN** the worker exits with a non-zero status and a clear error message

### Requirement: Transport envelope deserialization
The worker MUST deserialize inbound queue messages as the transport envelope defined in `event-ingestion`: `source`, `ingressId`, `receivedAt`, and `rawPayload`.

#### Scenario: Valid ADO transport message
- **WHEN** the worker receives a message with `source: "ado"` and all required envelope fields
- **THEN** it deserializes the message into a transport envelope model

#### Scenario: Valid GitHub transport message
- **WHEN** the worker receives a message with `source: "github"` and all required envelope fields
- **THEN** it deserializes the message into a transport envelope model

#### Scenario: Malformed transport message
- **WHEN** the worker receives a message missing required envelope fields or with invalid JSON
- **THEN** it dead-letters the message

### Requirement: Existing queue reference only
The worker MUST consume from a pre-provisioned Service Bus queue. This change MUST NOT create, alter, or delete Service Bus queues or namespaces.

#### Scenario: Queue consumption
- **WHEN** transport messages are available on the configured queue
- **THEN** the worker receives them without provisioning queue infrastructure

### Requirement: Transport integration tests
The repository MUST include integration tests that publish transport envelope fixtures to the configured or emulated Service Bus queue and assert the worker consumes and completes them.

#### Scenario: ADO fixture end-to-end
- **WHEN** an integration test publishes an ADO transport envelope fixture to the queue
- **THEN** the worker receives and completes the message

#### Scenario: GitHub fixture end-to-end
- **WHEN** an integration test publishes a GitHub transport envelope fixture to the queue
- **THEN** the worker receives and completes the message

### Requirement: Slice-1 completion without normalization
In this implementation slice, after successful transport envelope validation the worker MUST complete the message without performing lifecycle normalization, sync state access, or Snyk side effects.

#### Scenario: Valid envelope in slice 1
- **WHEN** the worker validates a transport envelope during this implementation slice
- **THEN** it completes the message without normalization or sync actions
