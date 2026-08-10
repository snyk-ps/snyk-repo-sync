# Contributing

This document is for people who create an application from this template or change code in this repository. End users and operators should start with the [README](README.md): **[Installation and setup](README.md#installation-and-setup)** for local use, and **[Deployment](README.md#deployment)** for the Azure Container App runbook (portal steps live in README, not here).

## Using this template

Use this template only for **Python** projects. It ships with Python 3.12+, `pyproject.toml`, `uv.lock`, a `src/` package layout, and Python-specific tooling (pytest, Dockerfile with uv, and Python-focused CI). If you need a template for another language, use a different starter repository.

### General setup

1. **Create a repository** from this template (or fork and clone) into your own org or account.
2. **Rename and describe the project** in [README.md](README.md): replace the title, description, and user-facing sections with your application's real name and documentation. Keep `TEMPLATE_VERSION` (or record it in your docs) so you always know which template revision you started from. When you want **Release Please** and **Docker publishing** for your app, delete `.github/template` (that file keeps automation off for the template repository itself) and add a root `VERSION` file with one semver line (for example `0.1.0`). Release Please `release-type: simple` reads `VERSION`; that file is for **your application**, not the template. The template does not ship `VERSION`.
3. **Python 3.12+** and **[uv](https://docs.astral.sh/uv/getting-started/installation/)** for dependencies. Declare packages in `pyproject.toml` and commit `uv.lock` so installs are reproducible (`uv lock` / `uv sync`). **Scan dependencies with Snyk** (or your team's process) before merging; do not ship high- or critical-severity issues from those dependencies.
4. **Implement** under `src/` and add **unit tests** under `tests/` as you go ([Test layout](#test-layout)). Use `data/` for local fixtures and artifacts and `scripts/` for one-off tooling (see [Project layout](#project-layout)). The layout here is a starting point; change it to match your package structure.

### AI Coding Assistant Setup

This template assumes you use **[Cursor](https://cursor.com/)** as your IDE. `.cursor/rules/` encodes project conventions (including the OpenSpec workflow), and those rules are written for Cursor's agent. You can work in another editor, but you will need to apply the same conventions yourself.

**OpenSpec** drives spec-first changes in this repo. After you clone or create your app from the template:

- **Install** the OpenSpec CLI as described in the **[OpenSpec repository on GitHub](https://github.com/Fission-AI/OpenSpec)**.
- **Initialize** from the **repository root**:

  ```bash
  openspec init
  ```

  That initializes OpenSpec in your project (directories such as `openspec/`, project metadata, and editor integration as documented upstream).

- **Read** `openspec/project.md`, `openspec/AGENTS.md`, and the workflow in `.cursor/rules/openspec.mdc` before you implement features.

For background, issues, and releases, use the **[OpenSpec GitHub project](https://github.com/Fission-AI/OpenSpec)**.

Also load **secrets from environment variables** (for example `SNYK_TOKEN`) and follow `.cursor/rules/` for Python and API conventions beyond OpenSpec.

### Documentation cleanup

When your documentation is ready for readers of your application (not the template scaffold):

- In **[README.md](README.md)**, replace scaffold sections with your application's real install, usage, and deployment docs. Keep a short **[More documentation](README.md#more-documentation)** table if you still split operator and contributor guides.
- In **this file**, delete **Using this template** (including **General setup**, **AI Coding Assistant Setup**, and **Documentation cleanup**) once you no longer need template onboarding. Trim or rewrite **Template metadata** if it no longer applies.
- In **[CONFIGURATION.md](CONFIGURATION.md)**, replace placeholder tables and sections with your application's real configuration reference.

## Development setup

- **Python** 3.12 or newer (`requires-python` in `pyproject.toml`).
- **[uv](https://docs.astral.sh/uv/getting-started/installation/)** for dependencies (`pyproject.toml`, `uv.lock`).

From the repository root:

```bash
uv sync
```

To include dev dependencies (for example **pytest**):

```bash
uv sync --dev
```

Do not commit secrets. Use environment variables (for example **`SNYK_TOKEN`**) when exercising the app locally.

## Running tests

```bash
uv run pytest
```

Unit tests run by default. Integration tests are marked with `@pytest.mark.integration` and require Service Bus configuration.

```bash
# Unit tests only
uv run pytest -m "not integration"

# Integration tests (requires config + Azure credentials)
cp data/config.yaml.example data/config.yaml
# edit data/config.yaml with dev Service Bus and Table Storage settings
az login
uv run pytest -m integration
```

Integration tests publish native queue message fixtures from `data/fixtures/` to the configured queue and assert the worker completes them. They require `data/config.yaml` (or `WORKER_CONFIG_PATH`) and `DefaultAzureCredential` (`az login` or service principal with **Azure Service Bus Data Owner** and **Storage Table Data Contributor**). Use a dedicated test namespace — never run integration tests against production queues without understanding side effects.

Add test runners and tools as dev dependencies in `pyproject.toml` and sync with uv. Configure pytest so **`src`** is on the import path (for example `pythonpath = ["src"]` and `testpaths = ["tests"]` under `[tool.pytest.ini_options]`).

## Test layout

Unit tests live under **`tests/`** and **mirror the package path under `src/`**, not the literal `src/` directory name.

| Source module | Test module |
| ------------- | ------------- |
| `src/snyk/client.py` | `tests/snyk/test_client.py` |
| `src/commands/sync.py` | `tests/commands/test_sync.py` |
| `src/main.py` | `tests/test_main.py` |

Name test files `test_<module>.py` (pytest discovers `test_*.py` by default). Import application code as you would at runtime with `src` on the path—for example `from snyk.client import ...`, not `from src.snyk.client import ...`.

### Edge cases

- **`src/main.py`:** The CLI entry point sits at the root of `src/`, so its tests belong at **`tests/test_main.py`**, not under `tests/src/`.
- **Private modules:** Map `src/snyk/_internal.py` to **`tests/snyk/test_internal.py`** (drop the leading underscore in the test file name).
- **`__init__.py`:** Usually no dedicated test file unless the package init exposes real API worth asserting.
- **Large modules:** Prefer one `test_<module>.py` per source module; split into multiple test files under the same package directory only when a single file becomes unwieldy (for example `tests/snyk/test_client_auth.py` and `tests/snyk/test_client_retry.py`).
- **Shared fixtures:** Use **`tests/conftest.py`** or **`tests/<pkg>/conftest.py`**. These do not mirror a source file.
- **Integration tests:** Cross-module or end-to-end tests may live under **`tests/integration/`** instead of mirroring a single module.
- **`scripts/`:** Helpers outside `src/` are tested under **`tests/scripts/`** (for example `tests/scripts/test_generate_foo.py`) or via integration tests—not by mirroring `src/`.
- **`__init__.py` under `tests/`:** Avoid adding `__init__.py` in mirrored subdirectories such as `tests/snyk/` unless you have a specific reason; it can make test packages importable and confuse pytest collection.

## Project layout

| Path | Purpose |
| ---- | ------- |
| `src/commands/` | CLI commands and `argparse` entry points that wire user input to application logic. |
| `src/common/` | Shared helpers, types, and utilities used across packages (not tied to Snyk or a single integration). |
| `src/config/` | Configuration loading, defaults, and environment-driven settings. |
| `src/integrations/` | Third-party systems outside Snyk (for example GitHub): API clients, auth, and adapters that call external HTTP APIs. |
| `src/snyk/` | Snyk-specific code: the Snyk REST or v1 APIs, Snyk CLI usage, and anything that speaks Snyk's own surfaces. |

Entry point: **`src/main.py`**.

| Path | Purpose |
| ---- | ------- |
| `tests/` | Unit tests for `src/`; mirror package paths per [Test layout](#test-layout). |
| `data/` | Local fixtures, sample inputs, and small reference files. **Do not commit secrets.** Prefer resolving paths via `config/` or env vars rather than hardcoding absolute locations. |
| `scripts/` | Executable helpers that are **not** the shipped Python package: one-off migrations, data import/export, local dev wrappers, or operational tasks you run from a shell or `uv run`. |

## OpenSpec and specifications

This repo uses **OpenSpec** for spec-driven changes:

1. Read **`openspec/project.md`** and **`openspec/AGENTS.md`** for project context and agent workflow.
2. Follow **`.cursor/rules/openspec.mdc`**: propose an approved change under **`openspec/changes/`** before implementation, then apply and archive per project rules.
3. Follow **`.cursor/rules/guidelines.mdc`** for Python 3.12+, uv, secrets via env vars, and tests.

## CI, releases, and containers

**`.github/workflows/`** wires releases and container publishing. Adjust or remove workflows if your process differs. **Azure Container App deployment** (identity, config mount, secrets, scaling) is documented in **[README § Deployment](README.md#deployment)** — this section covers Dockerfile and CI only.

**Template marker:** The file `.github/template` exists in this repository so **GitHub Actions do not run** Release Please or Docker publish here. That avoids versioning this project as a shipped template artifact. When someone creates **an application** from the template, they delete `.github/template`, add `VERSION` at the repo root (single semver line), and workflows then run as usual.

### Dockerfile

The root `Dockerfile` uses a **multi-stage** build: dependencies are installed with **uv** in a builder stage, then the app runs in a slim final image without the uv binary.

| Item | Detail |
| ---- | ------ |
| Builder | `ghcr.io/astral-sh/uv:python3.12-bookworm-slim` runs `uv sync --locked` using `pyproject.toml` and `uv.lock` (bytecode compile and cache mounts as in the file). |
| Runtime | `python:3.12-slim-bookworm`; `PATH` includes `/app/.venv/bin`. The process runs as a non-root user (`nonroot`, uid/gid 999). |
| App layout | Full project is copied into `/app`; the default command is `python src/main.py`. |
| Build context | `.dockerignore` keeps unnecessary paths out of the image build (see that file for the exact list). |

Local build example (from the repository root):

```bash
docker build -t myapp:local .
docker run --rm myapp:local
```

Pass env vars and flags your CLI expects with `docker run -e ...` or your orchestrator's equivalent.

### GitHub Actions

**`release.yml` (Docker publish)** runs when you **push a tag** matching `v*.*.*` (for example `v1.2.3`), and only when `.github/template` is absent. It checks out the repo, logs in to **GitHub Container Registry** (`ghcr.io`) with `GITHUB_TOKEN`, builds `Dockerfile`, and **pushes** the image as:

`ghcr.io/<owner>/<repository>:<tag>`

using the **git tag name** as the image tag (for example `ghcr.io/my-org/my-repo:v1.2.3`; GHCR uses the repository's lowercase name). It also **creates a GitHub Release** for that tag. Mark tags with a hyphen as prereleases (see the workflow). Ensure the repository allows **GitHub Packages** and that consumers authenticate to `ghcr.io` when pulling private images.

**Typical flow (after you delete `.github/template` and add `VERSION`):** merge work to `main` → create and push new version tag → `release.yml` builds and pushes the Docker image to GHCR.

## Template metadata

The root **`TEMPLATE_VERSION`** file holds a single **semver line** for **this project template** (not your application's release). When someone creates an app from the template, that value records **which template revision** they started from, which helps with support, upgrades, and comparing to newer template releases.

**`VERSION`** (which you add for Release Please) is your **app's** version. **`TEMPLATE_VERSION`** is **lineage metadata** only; it does not drive Release Please or Docker tags. Template maintainers bump `TEMPLATE_VERSION` when they publish meaningful template changes; app teams may keep the file as-is or update it after merging template updates.
