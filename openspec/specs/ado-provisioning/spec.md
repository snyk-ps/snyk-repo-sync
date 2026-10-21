## Purpose

Provision ADO audit stream for Git repository lifecycle events per operator documentation.
## Requirements
### Requirement: Audit stream provisioning
Audit stream subscription for ADO Git repository lifecycle events MUST be provisioned per operator documentation (`INGESTION.md`): Event Grid topic, ADO organization audit stream, Event Grid subscription with `subject` and `data.ActionId` advanced filters, and direct delivery to the Service Bus queue.

#### Scenario: Audit stream setup
- **WHEN** an operator completes audit stream deployment per INGESTION.md
- **THEN** Git repository created, renamed, deleted, and default-branch-changed audit events flow from Event Grid to the Service Bus queue as native Event Grid JSON

### Requirement: ADO PAT usage
When `scopeMapping.azure-repos` contains one or more mappings, the worker MUST require `ado.organization` and `ADO_PAT` at startup and MUST use the PAT for metadata enrichment requiring ADO REST API access. The PAT MUST be stored in Key Vault or container secrets.

When `scopeMapping.azure-repos` is absent or empty, the worker MUST NOT require `ado.organization` or `ADO_PAT` at startup and MUST NOT construct an ADO API client.

The PAT MUST include **Code (Read)** scope (`Code` → Read in Azure DevOps) so the worker can call `GET .../_apis/git/repositories/{repositoryId}` to read `defaultBranch`. The PAT MUST have access to the configured ADO organization and to every mapped project that can emit lifecycle events processed by the worker.

#### Scenario: ADO mappings require credentials
- **WHEN** the worker starts with one or more `scopeMapping.azure-repos` entries
- **THEN** it requires a non-empty `ado.organization` and `ADO_PAT`

#### Scenario: GitHub-only startup without ADO credentials
- **WHEN** the worker starts without any `scopeMapping.azure-repos` entries and without `ado.organization` or `ADO_PAT`
- **THEN** startup succeeds without constructing an ADO API client

#### Scenario: Enrichment during processing
- **WHEN** the worker needs a repository default branch not present in the normalized ADO event or sync state and an ADO client is configured
- **THEN** it calls the ADO Git REST API using `ADO_PAT` without logging credentials

#### Scenario: Unexpected ADO enrichment without configured credentials
- **WHEN** an ADO event is routed without an explicit `azure-repos` mapping, its default branch is absent from the event and sync state, and no ADO client is configured
- **THEN** import does not proceed and the message is dead-lettered with a clear configuration error without guessing a branch or stopping the worker

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

