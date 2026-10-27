## ADDED Requirements

### Requirement: Fixed Azure transitive versions
The committed resolution in `uv.lock` MUST resolve `pyjwt` to at least 2.15.0, `urllib3` to at least 2.8.0, and `certifi` to at least 2026.10.19. Each resolved distribution MUST declare `requires-python` that includes Python 3.12. These three packages MUST be expressed as uv constraints, not as `[project] dependencies`. The direct Azure packages MUST remain `azure-data-tables`, `azure-identity`, `azure-servicebus`, and `azure-storage-queue`.

#### Scenario: PyJWT clears the 2.15.0 finding
- **WHEN** the lockfile is resolved for Python 3.12
- **THEN** `pyjwt` is at least 2.15.0 and its `requires-python` includes 3.12

#### Scenario: urllib3 and certifi meet their floors
- **WHEN** the lockfile is resolved for Python 3.12
- **THEN** `urllib3` is at least 2.8.0, `certifi` is at least 2026.10.19, and both declare `requires-python` that includes 3.12

#### Scenario: Direct Azure packages stay direct
- **WHEN** `pyproject.toml` is updated for this remediation
- **THEN** `[project] dependencies` still lists only the existing direct Azure packages for this tree, and `pyjwt`, `urllib3`, and `certifi` appear only as constraints

### Requirement: Azure dependency tree has no high or critical findings
The committed resolution in `uv.lock` MUST have no high or critical Snyk Open Source finding on a dependency path that includes `azure-data-tables`, `azure-identity`, `azure-servicebus`, or `azure-storage-queue`.

#### Scenario: Lockfile scan is clear
- **WHEN** Snyk Open Source scans the committed `uv.lock` with the Python 3.12 interpreter at high severity
- **THEN** no high or critical finding remains on a path that includes one of the four direct Azure packages

#### Scenario: Locked install still passes unit tests
- **WHEN** the remediated `pyproject.toml` and `uv.lock` are committed
- **THEN** `uv sync --locked` installs that resolution on Python 3.12 and `uv run pytest -m "not integration"` passes
