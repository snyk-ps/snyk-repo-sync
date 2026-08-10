## MODIFIED Requirements

### Requirement: ADO PAT usage
ADO PAT MUST be used for metadata enrichment requiring ADO REST API access; it MUST be stored in Key Vault or container secrets.

The PAT MUST include **Code (Read)** scope (`Code` → Read in Azure DevOps) so the worker can call `GET .../_apis/git/repositories/{repositoryId}` to read `defaultBranch`. The PAT MUST have access to the configured ADO organization and to every mapped project that can emit lifecycle events processed by the worker.

#### Scenario: Enrichment during processing
- **WHEN** the worker needs a repository default branch not present in the normalized event
- **THEN** it calls the ADO Git REST API using `ADO_PAT` without logging credentials

#### Scenario: Insufficient PAT scope
- **WHEN** the ADO Git REST API returns 401 or 403 for repository metadata lookup
- **THEN** import does not proceed and the failure is logged without exposing the PAT
