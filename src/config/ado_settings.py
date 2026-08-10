"""ADO REST API settings for repository metadata enrichment."""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass

from config.errors import ConfigError

ADO_ORGANIZATION_ENV = "ADO_ORGANIZATION"
ADO_HOST_ENV = "ADO_HOST"
ADO_PAT_ENV = "ADO_PAT"
DEFAULT_ADO_HOST = "dev.azure.com"


@dataclass(frozen=True)
class AdoSettings:
    """Azure DevOps organization settings for REST enrichment."""

    organization: str
    host: str = DEFAULT_ADO_HOST


def parse_ado_settings(
    raw: object,
    environ: Mapping[str, str] | None = None,
) -> AdoSettings:
    """Parse ADO settings from operator config with optional env overrides."""
    env = os.environ if environ is None else environ
    config_raw = raw if isinstance(raw, dict) else {}

    organization = env.get(ADO_ORGANIZATION_ENV, config_raw.get("organization"))
    host = env.get(ADO_HOST_ENV, config_raw.get("host", DEFAULT_ADO_HOST))

    if not isinstance(organization, str) or not organization.strip():
        raise ConfigError(
            f"Missing or invalid required setting: ado.organization or {ADO_ORGANIZATION_ENV}",
        )
    if not isinstance(host, str) or not host.strip():
        raise ConfigError(
            f"Missing or invalid setting: ado.host or {ADO_HOST_ENV}",
        )

    return AdoSettings(
        organization=organization.strip(),
        host=host.strip().rstrip("/"),
    )


def require_ado_pat(environ: Mapping[str, str] | None = None) -> str:
    """Return the ADO PAT from the environment.

    Raises:
        ConfigError: When ``ADO_PAT`` is missing or empty.
    """
    env = os.environ if environ is None else environ
    token = env.get(ADO_PAT_ENV)
    if not isinstance(token, str) or not token.strip():
        raise ConfigError(f"Missing or empty required environment variable: {ADO_PAT_ENV}")
    return token.strip()
