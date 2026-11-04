## MODIFIED Requirements

### Requirement: Operator Snyk settings in config
The worker MUST load optional `snyk` settings from operator config at startup: `maxConcurrentPendingImports` (default 100), `migrateIgnores` (boolean, default `true`), and `targetRemoval` with keys `onRename`, `onDefaultBranchChange`, `onRepoDelete`, and `onIgnore` (each `deactivate` or `delete`, default `deactivate`) and `onUpdate` (`deactivate`, `delete`, or `none`, default `none`).

Invalid removal mode values MUST cause startup failure. A non-boolean `snyk.migrateIgnores` MUST cause startup failure.

The worker MUST require `SNYK_TOKEN` from the environment when Snyk sync is enabled for mapped ADO processing.

#### Scenario: Default Snyk settings
- **WHEN** `snyk` section is absent from config
- **THEN** the worker uses `maxConcurrentPendingImports=100`, `migrateIgnores=true`, deactivation for `onRename`, `onDefaultBranchChange`, `onRepoDelete`, and `onIgnore`, and `none` for `onUpdate`

#### Scenario: Missing SNYK_TOKEN at startup
- **WHEN** the worker starts without `SNYK_TOKEN` set
- **THEN** it exits with a non-zero status and a clear error message

#### Scenario: Migrate ignores disabled
- **WHEN** `snyk.migrateIgnores` is `false`
- **THEN** the worker loads that value and skips v1 project-ignore copies

#### Scenario: Invalid onUpdate fails startup
- **WHEN** `snyk.targetRemoval.onUpdate` is `skip`
- **THEN** the worker exits at startup with a configuration error

### Requirement: Custom property updated imports the GitHub repository
The worker MUST normalize the parsed updated body in `data/fixtures/github_parsed_updated.json` to `repo.created` and MUST record on the normalized event that the body was a parsed updated import. It MUST run the GitHub create flow for that event, including a new import when the org-move rule in idempotency applies. This body is the import signal for the parsed updated contract. The worker MUST NOT require a GitHub `action: created` body before importing.

After that import completes, and when `snyk.migrateIgnores` is `true`, the worker MUST copy v1 project ignores from the Azure DevOps target identified by the extracted property value when that target exists. When `snyk.migrateIgnores` is `false`, the worker MUST skip that copy. The lookup MUST use integration type `azure-repos` in the resolved Snyk org, owner equal to that property value, repository name equal to the GitHub repository name, and branch equal to the import branch. That property value is the same value scope mapping used to select the Snyk org. A missing ADO target MUST skip the copy, MUST skip retirement, and MUST still leave the GitHub import complete.

After the copy succeeds, there is nothing to copy, or `snyk.migrateIgnores` is `false`, the worker MUST apply `snyk.targetRemoval.onUpdate` to that Azure DevOps target. `none` MUST leave the target in place. `deactivate` MUST deactivate every project on that target. `delete` MUST delete that target. The worker MUST NOT retire the target while the copy has failed or is still pending. A retirement failure MUST retry `ignore_migration` and MUST NOT start another import.

The worker MUST NOT deactivate or delete the previous GitHub target. It MUST NOT persist a standing link from the GitHub repository to an ADO project or ADO target. In-flight migration fields cleared at the end of the attempt, including after retirement, are not a standing link.

#### Scenario: Updated body imports the GitHub repository
- **WHEN** the worker receives `data/fixtures/github_parsed_updated.json` and scope mapping resolves a Snyk org
- **THEN** it runs the GitHub `repo.created` import path for that body's `repository` and records the event as a parsed updated import

#### Scenario: Updated import copies ADO project ignores
- **WHEN** `snyk.migrateIgnores` is `true`, `snyk.targetRemoval.onUpdate` is `none`, and the GitHub updated event imports a repository and an `azure-repos` target exists for the extracted property value, the GitHub repository name, and the import branch
- **THEN** the worker copies v1 project ignores from that ADO target onto the new GitHub projects and does not deactivate or delete the ADO target

#### Scenario: Updated import leaves ADO targets in place
- **WHEN** `snyk.targetRemoval.onUpdate` is `none` and the GitHub updated event imports a repository whose extracted property value names an ADO project that already has a Snyk target
- **THEN** the worker does not deactivate or delete that ADO target

#### Scenario: Updated import with no ADO target
- **WHEN** the GitHub updated event imports a repository and no matching `azure-repos` target exists
- **THEN** the worker completes the GitHub import, skips the ignore copy, does not retire a target, and does not fail the message

#### Scenario: Delete ADO target after updated copy
- **WHEN** `snyk.targetRemoval.onUpdate` is `delete` and the updated import has copied v1 project ignores from the matching Azure DevOps target
- **THEN** the worker deletes that Azure DevOps target and does not delete the GitHub target

#### Scenario: Disabled copy still retires the ADO target
- **WHEN** `snyk.migrateIgnores` is `false`, `snyk.targetRemoval.onUpdate` is `deactivate`, and the matching Azure DevOps target exists
- **THEN** the worker does not call the v1 project-ignores API and deactivates every project on that Azure DevOps target

#### Scenario: Copy failure does not retire the ADO target
- **WHEN** `snyk.targetRemoval.onUpdate` is `delete` and the v1 ignore API fails during the updated import's ignore migration
- **THEN** the worker reschedules `ignore_migration` and does not delete the Azure DevOps target
