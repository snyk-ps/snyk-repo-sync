# Python Project Template

## Description

**This is a Python-only project template.** It is not a multi-language or language-agnostic starter—use it when you are building a Python 3.12+ application with `uv`, `src/` layout, and the conventions documented here.

**Note:** In the template repository, this file is a **README scaffold**. When you build a custom application from the template, replace the title and sections below with that application's real name, setup, and documentation.

This section provides a high-level overview of the project. It should clearly and concisely explain the project's purpose, functionality, and the problem it aims to solve.

## Table of contents

- [Installation and setup](#installation-and-setup)
- [Configuration](#configuration)
- [Usage](#usage)
- [Features](#features)
- [Testing](#testing)
- [Troubleshooting](#troubleshooting)
- [Deployment](#deployment)
- [More documentation](#more-documentation)

## Installation and setup

Replace this section with real install steps for your application.

### Prerequisites

- **Python** 3.12+ and **[uv](https://docs.astral.sh/uv/getting-started/installation/)** for dependencies (`pyproject.toml`, `uv.lock`).
- List any other required tools, services, or API access your application needs.

### Development / local installation

Use this path to run the application on your workstation.

1. **Clone** the repository and install dependencies:

```bash
uv sync
```

For tests and optional dev dependencies: **`uv sync --dev`** (see **[CONTRIBUTING.md](CONTRIBUTING.md)**).

2. **Configure** the application per **[CONFIGURATION.md](CONFIGURATION.md)**. Load **secrets from environment variables** (for example **`SNYK_TOKEN`**); never commit credentials.

3. **Verify** the install (adjust commands after you extend the CLI):

```bash
uv run python src/main.py --help
uv run pytest
```

Optional: build and run the root **`Dockerfile`** locally to mirror production; image and CI notes are in **[CONTRIBUTING.md](CONTRIBUTING.md)**.

### Deployment / production installation

Use this path for production containers or scheduled jobs.

1. **Image:** build from this repo's **`Dockerfile`**, or pull a release image from **[GitHub Container Registry](https://docs.github.com/en/packages/working-with-a-github-packages-registry/working-with-the-container-registry)** (`ghcr.io`) after you enable release workflows (see **[CONTRIBUTING.md § CI, releases, and containers](CONTRIBUTING.md#ci-releases-and-containers)**).
2. **Secrets:** inject via your platform's secret store, not in the image or committed config.
3. **Configuration:** mount or supply non-secret settings per **[CONFIGURATION.md](CONFIGURATION.md)**.

## Configuration

- Non-secret settings live in configuration files and/or environment variables documented in **[CONFIGURATION.md](CONFIGURATION.md)**. **Never** put API tokens or passwords in committed config.
- Precedence, file keys, env vars, and CLI flags: **[CONFIGURATION.md](CONFIGURATION.md)**.
- Replace this bullet list with a short summary of how operators configure your application in production.

## Usage

Replace with how to run and use the application. From the repository root, after `uv sync`, the scaffold entry point is:

```bash
uv run python src/main.py --help
```

Adjust after you add arguments or package the app. Command-level detail belongs in **[CONFIGURATION.md](CONFIGURATION.md)**.

## Features

Replace with a concise list of what the project does.

## Testing

From the repository root:

```bash
uv run pytest
```

Add test runners and tools as dev dependencies in `pyproject.toml` and sync with uv. Layout and contributor expectations: **[CONTRIBUTING.md § Test layout](CONTRIBUTING.md#test-layout)**.

## Troubleshooting

Common errors, known issues, FAQ, and debugging tips. Link to **[CONFIGURATION.md](CONFIGURATION.md)** for configuration-specific mistakes (missing env vars, wrong file paths, and similar).

## Deployment

Where and how you deploy in production: environment variables, secrets, and runtime config.

For containers, images built by **`release.yml`** are published to **`ghcr.io`** (GitHub Container Registry) after you delete **`.github/template`**, add **`VERSION`**, and tag releases. Pull and run that image in your environment or wire the registry into Kubernetes, ECS, or another orchestrator.

Sizing, Dockerfile stages, and GitHub Actions: **[CONTRIBUTING.md § CI, releases, and containers](CONTRIBUTING.md#ci-releases-and-containers)**.

## More documentation

| Document | Audience |
| -------- | -------- |
| **[CONFIGURATION.md](CONFIGURATION.md)** | Full configuration reference: files, env vars, CLI flags, commands. |
| **[CONTRIBUTING.md](CONTRIBUTING.md)** | Template setup, project layout, OpenSpec, tests, CI/Docker, **`TEMPLATE_VERSION`**. |
