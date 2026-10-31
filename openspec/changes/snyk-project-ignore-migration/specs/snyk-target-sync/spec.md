## MODIFIED Requirements

### Requirement: Deactivate over delete
Target removal mode MUST be configurable in operator config under `snyk.targetRemoval` for repository rename, default branch change, repository deletion, and ignored-repository enforcement. Allowed values: `deactivate` or `delete`. Default MUST be `deactivate` when unset.

Keys: `onRename`, `onDefaultBranchChange`, `onRepoDelete`, and `onIgnore`.

Repository deletion and ignore-policy enforcement MUST remove the whole target. When removal mode is `deactivate`, the integration MUST deactivate every Snyk project associated with the target via the v1 Projects API (`POST /v1/org/{orgId}/project/{projectId}/deactivate`). When removal mode is `delete`, the integration MUST delete the target via the REST Targets API (`DELETE /rest/orgs/{org_id}/targets/{target_id}`).

Rename and default branch change MUST snapshot the source, start the new import, and MUST NOT retire the source until the import has completed and v1 project-ignore migration has succeeded or been skipped. Removal failure after that import MUST retry retirement and MUST NOT start another import.

On rename, retirement MUST apply to the previous target. `deactivate` MUST deactivate every project on that target. `delete` MUST delete that target.

On default branch change, the previous branch and the new branch are `target_reference` values on one target. Retirement MUST apply only to projects on that target whose `target_reference` is the previous branch. `deactivate` MUST deactivate those projects. `delete` MUST delete those projects via `DELETE /rest/orgs/{org_id}/projects/{project_id}` and MUST NOT delete the target.

#### Scenario: Resolve target id after import
- **WHEN** an import job completes but repository state has no `snykTargetId`
- **THEN** the worker resolves the target id via the REST Targets API and persists it before marking import complete

#### Scenario: Resolve target id before removal
- **WHEN** a rename, default branch change, or delete event is processed and `snykTargetId` is empty in state
- **THEN** the worker resolves the target id via REST lookup using the appropriate repository name and branch for the old target

#### Scenario: Retirement failure does not start another import
- **WHEN** source retirement fails after a successful rename or default-branch import and ignore migration
- **THEN** the worker does not start another import and surfaces the error for retry or dead-letter

#### Scenario: Default removal mode
- **WHEN** `snyk.targetRemoval` is absent
- **THEN** rename, default branch change, repo delete, and ignore enforcement all use deactivation

#### Scenario: Delete on repo removal
- **WHEN** `snyk.targetRemoval.onRepoDelete` is `delete` and a repo-deleted event is processed
- **THEN** the Snyk target is hard-deleted and repository state reflects inactive status with no active target id

#### Scenario: Delete previous target after rename copy
- **WHEN** `snyk.targetRemoval.onRename` is `delete` and a repo-renamed event has finished importing the new name and migrating or skipping v1 project ignores
- **THEN** the previous Snyk target is deleted

#### Scenario: Deactivate previous branch projects after default branch copy
- **WHEN** `snyk.targetRemoval.onDefaultBranchChange` is `deactivate` and a default-branch-changed event with a prior default branch has finished importing the new branch and migrating or skipping v1 project ignores
- **THEN** the worker deactivates only the projects whose `target_reference` is the previous branch, and the target remains

#### Scenario: Delete previous branch projects keeps the target
- **WHEN** `snyk.targetRemoval.onDefaultBranchChange` is `delete` and a default-branch-changed event has finished importing the new branch and migrating or skipping v1 project ignores
- **THEN** the worker deletes only the projects whose `target_reference` is the previous branch and does not delete the target

#### Scenario: Ignored repo with active target
- **WHEN** ignore policy matches a repository with an active synced target
- **THEN** the target is removed per `snyk.targetRemoval.onIgnore`

#### Scenario: Delete on ignore match
- **WHEN** `snyk.targetRemoval.onIgnore` is `delete` and a repository matches ignore policy with an active target
- **THEN** the Snyk target is hard-deleted and repository state reflects inactive status

### Requirement: Required Snyk API operations
The integration MUST support: Import API (trigger + poll), Targets API (deactivate, delete, list), project listing with `type`, `target_file`, and `target_reference`, v1 project-ignore read and create, project delete for default-branch `delete` mode, and integration listing for ADO and GitHub integration resolution.

Project tagging via the Projects API is deferred to the `snyk-project-tagging` follow-up change and MUST NOT be called in this implementation slice.

#### Scenario: Repo rename flow without tagging
- **WHEN** a rename is processed in this slice
- **THEN** a new target is imported on the new name, v1 project ignores are migrated or skipped, the previous target is removed per configured removal mode, and project tagging is not performed

### Requirement: Credential scope
Snyk operations MUST use a token with permissions for import, deactivate, delete (when configured), list targets, list projects, read v1 project ignores in the source org, create v1 project ignores in the destination org, and list integrations, retrieved from Key Vault or container secrets via the `SNYK_TOKEN` environment variable.

#### Scenario: Worker startup
- **WHEN** the worker needs Snyk access
- **THEN** it retrieves the token from the configured secret store without logging the secret

## REMOVED Requirements

### Requirement: No ignore migration
**Reason**: v1 project ignores are copied by the `snyk-project-ignore-migration` capability before the source is retired.
**Migration**: Use the v1 project-ignore copy for rename, default branch change, and GitHub updated. Code consistent ignores remain unchanged.
