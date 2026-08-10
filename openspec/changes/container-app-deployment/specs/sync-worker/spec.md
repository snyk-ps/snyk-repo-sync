## ADDED Requirements

### Requirement: Operator Azure Container App deployment documentation
Operator documentation MUST describe deploying the worker as an Azure Container App with: managed identity, RBAC roles for Service Bus and Table Storage, config file mount at `/config/config.yaml`, secret injection for `SNYK_TOKEN` and `ADO_PAT`, and optional KEDA Service Bus scaling for replica count based on queue depth. Documentation MUST NOT document Container App Job deployment.

#### Scenario: Operator deploys worker to Azure
- **WHEN** an operator follows README deployment guidance after completing INGESTION.md queue setup
- **THEN** they can configure a Container App with identity, secrets, config mount, and queue connection settings without reading application source code

#### Scenario: Operator enables queue-driven scaling
- **WHEN** an operator reads optional KEDA scaling guidance in README deployment documentation
- **THEN** they can configure a Service Bus message-count scaler without changing worker application code
