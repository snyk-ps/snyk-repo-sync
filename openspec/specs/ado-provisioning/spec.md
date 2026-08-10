## Purpose

Provision ADO audit stream for Git repository lifecycle events per operator documentation.
## Requirements
### Requirement: Audit stream provisioning
Audit stream subscription for ADO Git repository lifecycle events MUST be provisioned per operator documentation (`INGESTION.md`): Event Grid topic, ADO organization audit stream, Event Grid subscription with `subject` and `data.ActionId` advanced filters, and direct delivery to the Service Bus queue.

#### Scenario: Audit stream setup
- **WHEN** an operator completes audit stream deployment per INGESTION.md
- **THEN** Git repository created, renamed, deleted, and default-branch-changed audit events flow from Event Grid to the Service Bus queue as native Event Grid JSON

### Requirement: ADO PAT usage
ADO PAT MUST be used for metadata enrichment requiring ADO REST API access; it MUST be stored in Key Vault or container secrets.

The PAT MUST include **Code (Read)** scope (`Code` → Read in Azure DevOps) so the worker can call `GET .../_apis/git/repositories/{repositoryId}` to read `defaultBranch`. The PAT MUST have access to the configured ADO organization and to every mapped project that can emit lifecycle events processed by the worker.

#### Scenario: Enrichment during processing
- **WHEN** the worker needs a repository default branch not present in the normalized event
- **THEN** it calls the ADO Git REST API using `ADO_PAT` without logging credentials

#### Scenario: Insufficient PAT scope
- **WHEN** the ADO Git REST API returns 401 or 403 for repository metadata lookup
- **THEN** import does not proceed and the failure is logged without exposing the PAT

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

