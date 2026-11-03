## MODIFIED Requirements

### Requirement: Deactivate over delete
Target removal mode MUST be configurable in operator config under `snyk.targetRemoval` for repository rename, default branch change, repository deletion, ignored-repository enforcement, and parsed GitHub updated imports. For `onRename`, `onDefaultBranchChange`, `onRepoDelete`, and `onIgnore`, allowed values are `deactivate` or `delete`, and the default MUST be `deactivate` when unset. For `onUpdate`, allowed values are `deactivate`, `delete`, or `none`, and the default MUST be `none` when unset. `none` MUST NOT deactivate or delete a target.

Keys: `onRename`, `onDefaultBranchChange`, `onRepoDelete`, `onIgnore`, and `onUpdate`.

Repository deletion and ignore-policy enforcement MUST remove the whole target. When removal mode is `deactivate`, the integration MUST deactivate every Snyk project associated with the target via the v1 Projects API (`POST /v1/org/{orgId}/project/{projectId}/deactivate`). When removal mode is `delete`, the integration MUST delete the target via the REST Targets API (`DELETE /rest/orgs/{org_id}/targets/{target_id}`).

Rename and default branch change MUST snapshot the source, start the new import, and MUST NOT retire the source until the import has completed and v1 project-ignore migration has succeeded or been skipped. Removal failure after that import MUST retry retirement and MUST NOT start another import.

A parsed GitHub updated import MUST NOT retire the Azure DevOps target until the import has completed and v1 project-ignore migration has succeeded or been skipped. It MUST retire that target only when `snyk.targetRemoval.onUpdate` is `deactivate` or `delete`. Removal failure after that import MUST retry retirement and MUST NOT start another import.

On rename, retirement MUST apply to the previous target. `deactivate` MUST deactivate every project on that target. `delete` MUST delete that target.

On default branch change, the previous branch and the new branch are `target_reference` values on one target. Retirement MUST apply only to projects on that target whose `target_reference` is the previous branch. `deactivate` MUST deactivate those projects. `delete` MUST delete those projects via `DELETE /rest/orgs/{org_id}/projects/{project_id}` and MUST NOT delete the target.

On a parsed GitHub updated import, retirement MUST apply to the whole `azure-repos` target in the resolved Snyk org whose owner is the extracted property value, whose repository name is the GitHub repository name, and whose branch is the import branch. That property value is the same value scope mapping used to select the Snyk org. `deactivate` MUST deactivate every project on that target. `delete` MUST delete that target. `none` MUST leave that target in place. The previous GitHub target MUST remain.

#### Scenario: Resolve target id after import
- **WHEN** an import job completes but repository state has no `snykTargetId`
- **THEN** the worker resolves the target id via the REST Targets API and persists it before marking import complete

#### Scenario: Resolve target id before removal
- **WHEN** a rename, default branch change, or delete event is processed and `snykTargetId` is empty in state
- **THEN** the worker resolves the target id via REST lookup using the appropriate repository name and branch for the old target

#### Scenario: Retirement failure does not start another import
- **WHEN** source retirement fails after a successful rename, default-branch, or GitHub updated import and ignore migration, and for the updated import `snyk.targetRemoval.onUpdate` is `deactivate` or `delete`
- **THEN** the worker does not start another import and surfaces the error for retry or dead-letter

#### Scenario: Default removal mode
- **WHEN** `snyk.targetRemoval` is absent
- **THEN** rename, default branch change, repo delete, and ignore enforcement all use deactivation, and a parsed GitHub updated import does not retire the Azure DevOps target

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

#### Scenario: Updated import leaves the ADO target when unset
- **WHEN** `snyk.targetRemoval.onUpdate` is absent and a parsed GitHub updated import has finished importing and migrating or skipping v1 project ignores
- **THEN** the worker does not deactivate or delete the Azure DevOps target

#### Scenario: Deactivate ADO target after updated copy
- **WHEN** `snyk.targetRemoval.onUpdate` is `deactivate` and a parsed GitHub updated import has finished importing and migrating or skipping v1 project ignores for an existing `azure-repos` target
- **THEN** the worker deactivates every project on that Azure DevOps target and does not delete the target

#### Scenario: Delete ADO target after updated copy
- **WHEN** `snyk.targetRemoval.onUpdate` is `delete` and a parsed GitHub updated import has finished importing and migrating or skipping v1 project ignores for an existing `azure-repos` target
- **THEN** the worker deletes that Azure DevOps target

#### Scenario: Invalid updated removal mode fails startup
- **WHEN** `snyk.targetRemoval.onUpdate` is `destroy`
- **THEN** the worker exits at startup with a configuration error
