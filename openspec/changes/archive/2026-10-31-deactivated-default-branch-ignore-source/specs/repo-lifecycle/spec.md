## MODIFIED Requirements

### Requirement: Default branch changed
On default branch change, when a prior default branch is known and ignore policy does NOT apply, the service MUST import the new default branch onto the existing Snyk target, poll until import job completion, copy or skip v1 project ignores from projects whose `target_reference` is the previous branch onto projects whose `target_reference` is the new branch, and only then retire the previous branch's projects per configured `snyk.targetRemoval.onDefaultBranchChange` (default deactivate). The target MUST remain. Project tagging is deferred.

The copy MUST include previous-branch projects that are already deactivated. The worker MUST read v1 project ignores for those projects. Destination projects MUST be projects that are not deactivated.

When ignore policy applies, the service MUST remove the existing target per `snyk.targetRemoval.onIgnore` if active, MUST NOT re-import, and MUST complete the message.

For `source: ado`, when `previousDefaultBranch` is absent, the worker MUST NOT perform sync actions.

#### Scenario: ADO default branch update via audit stream
- **WHEN** an audit-stream default-branch-changed event with `source: "ado"` and a prior default branch is processed and ignore policy does not apply
- **THEN** the new default branch is imported on the existing target, v1 project ignores are copied or skipped from the previous branch's projects, and only those previous-branch projects are retired

#### Scenario: ADO first default branch only
- **WHEN** an audit-stream default-branch-changed event omits `previousDefaultBranch`
- **THEN** the worker completes without project retirement or import

#### Scenario: GitHub default branch update via webhook
- **WHEN** a default-branch-changed event with `source: "github"` is processed with a prior default branch and ignore policy does not apply
- **THEN** the new default branch is imported on the existing target, v1 project ignores are copied or skipped, and only the previous branch's projects are retired

#### Scenario: Previous branch already deactivated
- **WHEN** a default-branch change has imported the new branch, the previous branch's projects are already deactivated, and the v1 ignores API still returns ignores for those projects
- **THEN** the worker copies those ignores onto the active projects whose `target_reference` is the new branch and does not skip the migration because the source projects are deactivated

#### Scenario: Default branch change on ignored repo
- **WHEN** a default-branch-changed event with a prior default branch is processed for a repository matching ignore policy
- **THEN** the worker removes the existing target per `snyk.targetRemoval.onIgnore` if active and does not re-import
