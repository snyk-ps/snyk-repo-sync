## MODIFIED Requirements

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
- **THEN** import does not proceed and message processing fails with a clear configuration error without guessing a branch

#### Scenario: Insufficient PAT scope
- **WHEN** the ADO Git REST API returns 401 or 403 for repository metadata lookup
- **THEN** import does not proceed and the failure is logged without exposing the PAT
