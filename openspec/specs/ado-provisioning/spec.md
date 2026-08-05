## Purpose

Provision ADO service hooks via pipeline script and audit stream via PS deployment.

## Requirements

### Requirement: Service hook provisioning via pipeline script
Service hooks for repository created, renamed, and deleted MUST be provisioned by a Python script executed inside an ADO pipeline.

#### Scenario: Initial project setup
- **WHEN** an operator runs the provisioning pipeline for an ADO project
- **THEN** the required service hooks are registered to forward events to the ingestion endpoint, which publishes normalized messages with `source: "ado"` to the Service Bus queue

### Requirement: Audit stream provisioning by PS
Default-branch audit stream subscription MUST be deployed by Snyk Professional Services (not customer self-service in v1).

#### Scenario: Audit stream setup
- **WHEN** PS completes audit stream deployment
- **THEN** default-branch change events flow to Event Grid and onward to the Service Bus queue

### Requirement: ADO PAT usage
ADO PAT MUST be used for metadata enrichment and reconciliation operations requiring ADO REST API access; it MUST be stored in Key Vault or container secrets.

#### Scenario: Enrichment during processing
- **WHEN** the worker needs ADO metadata not present in the event envelope
- **THEN** it calls ADO REST API using the configured PAT without logging credentials

### Requirement: Default branch detection mode
Default branch changes MUST be detected via audit stream only; reconciliation polling is out of scope for v1.

#### Scenario: Branch change without audit event
- **WHEN** default branch changes but no audit event is delivered
- **THEN** the service does not automatically re-import until an audit event is received
