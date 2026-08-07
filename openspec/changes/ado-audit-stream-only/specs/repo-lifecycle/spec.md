## MODIFIED Requirements

### Requirement: Repo created
On repository created, the service MUST import the repository and apply the repository id project tag, unless the repo matches ignore policy.

#### Scenario: New repo in mapped ADO project
- **WHEN** an audit-stream repo-created event with `source: "ado"` is processed for a non-ignored repository
- **THEN** the worker imports the repo and applies the tag

#### Scenario: New repo in mapped GitHub org
- **WHEN** a repo-created event with `source: "github"` is processed for a non-ignored repository
- **THEN** the worker imports the repo and applies the tag

### Requirement: Repo renamed
On repository renamed, the service MUST deactivate the old target, import under the new name, and apply the repository id project tag.

#### Scenario: Repository rename in ADO
- **WHEN** an audit-stream repo-renamed event with `source: "ado"` is processed
- **THEN** the old Snyk target is deactivated and a new target is imported with tag on the new name

#### Scenario: Repository rename in GitHub
- **WHEN** a repo-renamed event with `source: "github"` is processed
- **THEN** the old Snyk target is deactivated and a new target is imported with tag on the new name

### Requirement: Repo deleted
On repository deleted, the service MUST deactivate the corresponding Snyk target.

#### Scenario: Repository removed from ADO
- **WHEN** an audit-stream repo-deleted event with `source: "ado"` is processed
- **THEN** the Snyk target is deactivated and repository state reflects inactive status

#### Scenario: Repository removed from GitHub
- **WHEN** a repo-deleted event with `source: "github"` is processed
- **THEN** the Snyk target is deactivated and repository state reflects inactive status
