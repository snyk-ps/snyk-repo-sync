"""Tests for ADO settings parsing."""

from pathlib import Path

import pytest
import yaml

from config.ado_settings import (
    ADO_HOST_ENV,
    ADO_ORGANIZATION_ENV,
    ADO_PAT_ENV,
    parse_ado_settings,
    require_ado_pat,
)
from config.errors import ConfigError
from config.settings import load_worker_settings


def test_parse_ado_settings_from_config() -> None:
    settings = parse_ado_settings({"organization": "contoso", "host": "dev.azure.com"})

    assert settings.organization == "contoso"
    assert settings.host == "dev.azure.com"


def test_parse_ado_settings_env_overrides_config() -> None:
    settings = parse_ado_settings(
        {"organization": "file-org", "host": "file-host"},
        {
            ADO_ORGANIZATION_ENV: "env-org",
            ADO_HOST_ENV: "env-host",
        },
    )

    assert settings.organization == "env-org"
    assert settings.host == "env-host"


def test_parse_ado_settings_requires_organization() -> None:
    with pytest.raises(ConfigError, match="ado.organization"):
        parse_ado_settings({})


def test_require_ado_pat_success() -> None:
    assert require_ado_pat({ADO_PAT_ENV: "secret-pat"}) == "secret-pat"


def test_require_ado_pat_missing() -> None:
    with pytest.raises(ConfigError, match=ADO_PAT_ENV):
        require_ado_pat({})


def test_load_worker_settings_requires_ado_organization(tmp_path: Path) -> None:
    path = tmp_path / "config.yaml"
    path.write_text(
        yaml.safe_dump(
            {
                "serviceBus": {
                    "fullyQualifiedNamespace": "example.servicebus.windows.net",
                    "queueName": "repo-sync-events",
                },
                "syncState": {
                    "storageAccountEndpoint": "https://example.table.core.windows.net",
                },
            },
        ),
        encoding="utf-8",
    )

    with pytest.raises(ConfigError, match="ado.organization"):
        load_worker_settings(str(path))
