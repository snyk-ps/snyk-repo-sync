## MODIFIED Requirements

### Requirement: Operator Azure Container App deployment documentation
Operator documentation MUST describe deploying the worker as an Azure Container App with: managed identity, RBAC roles for Service Bus and Table Storage, config file mount at `/config/config.yaml`, secret injection for `SNYK_TOKEN` and `ADO_PAT`, and optional KEDA Service Bus scaling for replica count based on queue depth. Documentation MUST NOT document Container App Job deployment.

Operator documentation MUST reference the canonical container image **`ghcr.io/snyk-ps/snyk-repo-sync:<version>`** (where `<version>` is the release tag, e.g. `v0.1.0`).

README.md MUST place the **Deployment** section before local development / installation instructions so operators see production guidance first.

#### Scenario: Operator deploys worker to Azure
- **WHEN** an operator follows README deployment guidance after completing INGESTION.md queue setup
- **THEN** they can configure a Container App with identity, secrets, config mount, queue connection settings, and the GHCR image `ghcr.io/snyk-ps/snyk-repo-sync:<version>` without reading application source code

#### Scenario: Operator enables queue-driven scaling
- **WHEN** an operator reads optional KEDA scaling guidance in README deployment documentation
- **THEN** they can configure a Service Bus message-count scaler without changing worker application code

#### Scenario: Operator finds deployment before local setup
- **WHEN** an operator opens README.md
- **THEN** the Deployment runbook appears before local development / installation instructions
