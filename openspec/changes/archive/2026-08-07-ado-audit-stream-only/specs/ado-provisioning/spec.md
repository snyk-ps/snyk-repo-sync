## MODIFIED Requirements

### Requirement: Audit stream provisioning
Audit stream subscription for ADO Git repository lifecycle events MUST be provisioned per operator documentation (`INGESTION.md`): Event Grid topic, ADO organization audit stream, Event Grid subscription with lifecycle filters, and ingress handler to Service Bus.

#### Scenario: Audit stream setup
- **WHEN** an operator completes audit stream deployment per INGESTION.md
- **THEN** Git repository created, renamed, deleted, and default-branch-changed audit events flow to Event Grid and onward to the Service Bus queue

## ADDED Requirements

### Requirement: ADO lifecycle detection mode
ADO repository lifecycle changes MUST be detected via audit stream only; service hooks and reconciliation polling are out of scope for v1.

#### Scenario: Lifecycle change without audit event
- **WHEN** a repository lifecycle change occurs but no audit event is delivered
- **THEN** the service does not automatically sync until an audit event is received

### Requirement: Audit stream latency characteristics
Operators MUST be informed that ADO audit stream events are batched and typically delivered within 30 minutes or less. Documentation MUST state this latency is expected and acceptable for v1.

#### Scenario: Operator expects immediate sync after repo creation
- **WHEN** an operator creates a repository in ADO
- **THEN** documentation explains sync may not occur until the next audit batch is delivered to Event Grid
