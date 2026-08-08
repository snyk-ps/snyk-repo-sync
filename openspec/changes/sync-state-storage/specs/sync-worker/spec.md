## MODIFIED Requirements

### Requirement: Unknown scope handling
When an event references a scope (ADO project or GitHub org) with no `_meta` row, or with a `_meta` row where `enabled` is false, the worker MUST dead-letter the message with reason `UnknownScope` and emit an alert.

#### Scenario: Missing ADO project metadata
- **WHEN** a message arrives for an unknown ADO `scopeId`
- **THEN** the message is dead-lettered with reason `UnknownScope` and an alert is raised in Dynatrace

#### Scenario: Disabled ADO scope
- **WHEN** a message arrives for an ADO scope whose `_meta.enabled` is false
- **THEN** the message is dead-lettered with reason `UnknownScope` and an alert is raised in Dynatrace

#### Scenario: Missing GitHub org metadata
- **WHEN** a message arrives for an unknown GitHub `scopeId`
- **THEN** the message is dead-lettered with reason `UnknownScope` and an alert is raised in Dynatrace

### Requirement: Operator config and credential startup
The worker MUST authenticate to Azure Service Bus and Azure Table Storage using `DefaultAzureCredential`. It MUST load operator settings from the config file path supplied via `--config` (default `data/config.yaml`). The config file MUST exist. Service Bus and sync-state settings MAY be supplied in config and MAY be overridden by environment variables; env values MUST take precedence when set. Connection strings MUST NOT be supported or documented.

The runtime identity MUST be granted:
- **Azure Service Bus Data Owner** (or Azure Service Bus Data Receiver and Azure Service Bus Data Sender) on the queue or namespace — data plane only
- **Storage Table Data Contributor** on the storage account or table scope

The worker MUST fail fast when the config file path does not exist, when required settings are missing after config/env merge, or when credential initialization fails.

#### Scenario: Worker starts in production
- **WHEN** the container starts with `--config /config/config.yaml`, valid YAML, and a managed identity with required RBAC roles
- **THEN** it ensures the sync-state table exists, connects to the pre-provisioned queue, and begins receiving messages

#### Scenario: Local run with default config path
- **WHEN** a developer runs `worker run` without `--config`
- **THEN** the worker loads `data/config.yaml` and authenticates via `az login` (or configured dev principal)

#### Scenario: Local run with env override
- **WHEN** `data/config.yaml` exists and `SERVICEBUS_QUEUE_NAME` overrides the file value
- **THEN** the worker uses the env value for the queue name

#### Scenario: Missing config file
- **WHEN** `--config` points to a path that does not exist
- **THEN** the worker exits with a non-zero status and a clear error message

#### Scenario: Missing required setting after merge
- **WHEN** `serviceBus.fullyQualifiedNamespace` is absent in both config and env after merge
- **THEN** the worker exits with a non-zero status and a clear error message

## REMOVED Requirements

### Requirement: Environment-driven worker startup
**Reason:** Replaced by operator config with optional env overrides and DefaultAzureCredential for Azure services.
**Migration:** Configure `serviceBus` and `syncState` in operator config; assign RBAC roles to the runtime identity.

### Requirement: Slice-2 ADO normalization without sync
**Reason:** Replaced by slice-3 _meta lookup after ADO normalization.
**Migration:** Worker loads sync state and reads `_meta` before completing ADO messages.

## ADDED Requirements

### Requirement: Slice-3 ADO normalization with _meta lookup
In this implementation slice, after successful ADO lifecycle normalization the worker MUST load scope `_meta` from sync state for partition `{source}:{scopeId}`. When `_meta` is missing or `enabled` is false, the worker MUST dead-letter the message with reason `UnknownScope` and emit an alert. When `_meta` is present and enabled, the worker MUST log scope context and complete the message without Snyk side effects.

GitHub queue messages MUST be completed without normalization or sync side effects until GitHub normalization is implemented.

#### Scenario: Valid ADO message with known enabled scope
- **WHEN** the worker normalizes a supported ADO lifecycle message and `_meta` exists with `enabled: true`
- **THEN** it logs scope metadata and completes the message

#### Scenario: Valid ADO message with unknown scope
- **WHEN** the worker normalizes an ADO message and no `_meta` row exists for the scope partition
- **THEN** it dead-letters the message with reason `UnknownScope` and raises an operator alert
