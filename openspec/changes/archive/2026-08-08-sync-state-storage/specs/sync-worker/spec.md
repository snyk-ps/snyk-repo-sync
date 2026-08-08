## MODIFIED Requirements

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

## ADDED Requirements

### Requirement: Slice-3 ADO normalization with sync table only
In this implementation slice, after successful ADO lifecycle normalization the worker MUST log the normalized event and complete the message without scope mapping, repository state reads/writes, or Snyk side effects. The sync-state table MUST be ensured on startup for use by follow-up changes.

GitHub queue messages MUST be completed without normalization or sync side effects until GitHub normalization is implemented.

#### Scenario: Valid ADO message normalized in slice 3
- **WHEN** the worker parses and normalizes a supported ADO Event Grid lifecycle message
- **THEN** it logs normalized org, project, repository, and branch fields as applicable, then completes the message

#### Scenario: Valid GitHub message in slice 3
- **WHEN** the worker parses a valid GitHub webhook queue message
- **THEN** it completes the message without normalization or sync actions
