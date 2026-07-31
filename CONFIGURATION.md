# Configuration reference

Operator reference for configuration files, environment variables, and CLI flags. For installation, usage, and deployment, see the [README](README.md). For layout, tests, OpenSpec, and CI/Docker details, see **[CONTRIBUTING.md](CONTRIBUTING.md)**.

Replace this document with your application's real configuration reference as you implement features.

## Precedence

When the same logical setting exists in more than one place, document the resolution order for your application (**later wins** is a common pattern):

1. Built-in defaults
2. Configuration file (if your app uses one)
3. Environment variables
4. **CLI arguments** (highest precedence; useful for local smoke tests without editing files)

For **deployments**, keep authoritative values in configuration files or platform-injected environment. Use **CLI overrides** mainly for **local development** and one-off commands.

## Configuration files

Replace with the configuration files your application reads (for example YAML, TOML, or JSON under `src/config/`). Document each top-level key and nested fields in tables below as you add them.

Start from any sample config you ship under **`data/`** (add one when your app needs it).

## Environment variables

**Secrets** (API tokens, passwords, and similar) **must** come from environment variables or your secret store. **Never** commit them in configuration files or source.

| Variable | Required | Role |
| -------- | -------- | ---- |
| **`SNYK_TOKEN`** | When calling Snyk APIs | Snyk API token (**secret**; never commit). |

Add rows for every environment variable your application supports. Document defaults, overrides, and whether each value is secret or non-secret.

## CLI flags and parameters

The scaffold entry point is **`src/main.py`**. Document each important CLI flag: purpose, default, and examples.

Run:

```bash
uv run python src/main.py --help
```

Replace the placeholder table below as you add `argparse` arguments.

| Flag / parameter | Default | Purpose |
| ---------------- | ------- | ------- |
| *(add flags here)* | | |

## Commands

Document each CLI subcommand as you implement it: required configuration, secrets, and typical examples.

Example (scaffold only):

```bash
uv run python src/main.py --help
```

## Error handling and logging

Replace with how errors and logs behave, where logs go, and JSON log format if applicable. Cross-link from the [README troubleshooting section](README.md#troubleshooting) when you have operator-facing runbooks.
