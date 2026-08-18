"""Tests for unified worker configuration."""

from pathlib import Path

import pytest
import yaml

from config.settings import (
    DEFAULT_TABLE_NAME,
    SERVICEBUS_FQN_ENV,
    SERVICEBUS_QUEUE_ENV,
    SERVICEBUS_RECEIVE_MAX_WAIT_SECONDS_ENV,
    SNYK_TOKEN_ENV,
    SYNC_STATE_ENDPOINT_ENV,
    SYNC_STATE_TABLE_ENV,
    ConfigError,
    load_worker_settings,
    require_snyk_token,
)


def _write_config(tmp_path: Path, data: dict) -> str:
    path = tmp_path / "config.yaml"
    data.setdefault(
        "ado",
        {"organization": "example-org"},
    )
    path.write_text(yaml.safe_dump(data), encoding="utf-8")
    return str(path)


def test_load_worker_settings_success(tmp_path: Path) -> None:
    path = _write_config(
        tmp_path,
        {
            "serviceBus": {
                "fullyQualifiedNamespace": "example.servicebus.windows.net",
                "queueName": "repo-sync-events",
            },
            "syncState": {
                "storageAccountEndpoint": "https://example.table.core.windows.net",
            },
        },
    )

    settings = load_worker_settings(path)

    assert settings.service_bus.fully_qualified_namespace == "example.servicebus.windows.net"
    assert settings.service_bus.queue_name == "repo-sync-events"
    assert settings.service_bus.receive_max_wait_seconds == 5
    assert settings.sync_state.storage_account_endpoint == "https://example.table.core.windows.net"
    assert settings.sync_state.table_name == DEFAULT_TABLE_NAME
    assert settings.scope_mapping.default_snyk_org_id is None
    assert settings.scope_mapping.ado_by_project_name == {}
    assert settings.snyk.max_concurrent_pending_imports == 100
    assert settings.ado.organization == "example-org"


def test_load_worker_settings_with_scope_mapping(tmp_path: Path) -> None:
    path = _write_config(
        tmp_path,
        {
            "serviceBus": {
                "fullyQualifiedNamespace": "example.servicebus.windows.net",
                "queueName": "repo-sync-events",
            },
            "syncState": {
                "storageAccountEndpoint": "https://example.table.core.windows.net",
            },
            "scopeMapping": {
                "defaultSnykOrgId": "default-org",
                "azure-repos": [
                    {
                        "projectName": "proj",
                        "snykOrgId": "ado-org",
                    },
                ],
            },
        },
    )

    settings = load_worker_settings(path)

    assert settings.scope_mapping.default_snyk_org_id == "default-org"
    assert "proj" in settings.scope_mapping.ado_by_project_name


def test_load_worker_settings_rejects_duplicate_scope_mapping(tmp_path: Path) -> None:
    path = _write_config(
        tmp_path,
        {
            "serviceBus": {
                "fullyQualifiedNamespace": "example.servicebus.windows.net",
                "queueName": "repo-sync-events",
            },
            "syncState": {
                "storageAccountEndpoint": "https://example.table.core.windows.net",
            },
            "scopeMapping": {
                "azure-repos": [
                    {"projectName": "dup", "snykOrgId": "org-1"},
                    {"projectName": "dup", "snykOrgId": "org-2"},
                ],
            },
        },
    )

    with pytest.raises(ConfigError, match="Duplicate scopeMapping.azure-repos projectName"):
        load_worker_settings(path)


def test_load_worker_settings_env_overrides_config(tmp_path: Path) -> None:
    path = _write_config(
        tmp_path,
        {
            "serviceBus": {
                "fullyQualifiedNamespace": "file.servicebus.windows.net",
                "queueName": "file-queue",
            },
            "syncState": {
                "storageAccountEndpoint": "https://file.table.core.windows.net",
                "tableName": "FileTable",
            },
        },
    )

    settings = load_worker_settings(
        path,
        {
            SERVICEBUS_FQN_ENV: "env.servicebus.windows.net",
            SERVICEBUS_QUEUE_ENV: "env-queue",
            SYNC_STATE_ENDPOINT_ENV: "https://env.table.core.windows.net",
            SYNC_STATE_TABLE_ENV: "EnvTable",
        },
    )

    assert settings.service_bus.fully_qualified_namespace == "env.servicebus.windows.net"
    assert settings.service_bus.queue_name == "env-queue"
    assert settings.sync_state.storage_account_endpoint == "https://env.table.core.windows.net"
    assert settings.sync_state.table_name == "EnvTable"


def test_load_worker_settings_missing_file() -> None:
    with pytest.raises(ConfigError, match="Config file not found"):
        load_worker_settings("missing/config.yaml")


def test_load_worker_settings_missing_service_bus_namespace(tmp_path: Path) -> None:
    path = _write_config(
        tmp_path,
        {
            "serviceBus": {"queueName": "repo-sync-events"},
            "syncState": {
                "storageAccountEndpoint": "https://example.table.core.windows.net",
            },
        },
    )

    with pytest.raises(ConfigError, match="fullyQualifiedNamespace"):
        load_worker_settings(path)


def test_load_worker_settings_missing_sync_state_endpoint(tmp_path: Path) -> None:
    path = _write_config(
        tmp_path,
        {
            "serviceBus": {
                "fullyQualifiedNamespace": "example.servicebus.windows.net",
                "queueName": "repo-sync-events",
            },
            "syncState": {},
        },
    )

    with pytest.raises(ConfigError, match="storageAccountEndpoint"):
        load_worker_settings(path)


def test_load_worker_settings_invalid_yaml(tmp_path: Path) -> None:
    path = tmp_path / "config.yaml"
    path.write_text("serviceBus: [", encoding="utf-8")

    with pytest.raises(ConfigError, match="Invalid YAML"):
        load_worker_settings(str(path))


def test_require_snyk_token_success() -> None:
    assert require_snyk_token({SNYK_TOKEN_ENV: "secret-token"}) == "secret-token"


def test_require_snyk_token_missing() -> None:
    with pytest.raises(ConfigError, match=SNYK_TOKEN_ENV):
        require_snyk_token({})


def test_load_worker_settings_receive_max_wait_seconds_from_config(tmp_path: Path) -> None:
    path = _write_config(
        tmp_path,
        {
            "serviceBus": {
                "fullyQualifiedNamespace": "example.servicebus.windows.net",
                "queueName": "repo-sync-events",
                "receiveMaxWaitSeconds": 15,
            },
            "syncState": {
                "storageAccountEndpoint": "https://example.table.core.windows.net",
            },
        },
    )

    settings = load_worker_settings(path)

    assert settings.service_bus.receive_max_wait_seconds == 15


def test_load_worker_settings_receive_max_wait_seconds_env_override(tmp_path: Path) -> None:
    path = _write_config(
        tmp_path,
        {
            "serviceBus": {
                "fullyQualifiedNamespace": "example.servicebus.windows.net",
                "queueName": "repo-sync-events",
                "receiveMaxWaitSeconds": 15,
            },
            "syncState": {
                "storageAccountEndpoint": "https://example.table.core.windows.net",
            },
        },
    )

    settings = load_worker_settings(path, {SERVICEBUS_RECEIVE_MAX_WAIT_SECONDS_ENV: "30"})

    assert settings.service_bus.receive_max_wait_seconds == 30


@pytest.mark.parametrize(
    ("value", "match"),
    [
        (0, "must be an integer between 1 and 300"),
        (301, "must be an integer between 1 and 300"),
        ("not-a-number", "receiveMaxWaitSeconds"),
    ],
)
def test_load_worker_settings_rejects_invalid_receive_max_wait_seconds(
    tmp_path: Path,
    value: object,
    match: str,
) -> None:
    path = _write_config(
        tmp_path,
        {
            "serviceBus": {
                "fullyQualifiedNamespace": "example.servicebus.windows.net",
                "queueName": "repo-sync-events",
                "receiveMaxWaitSeconds": value,
            },
            "syncState": {
                "storageAccountEndpoint": "https://example.table.core.windows.net",
            },
        },
    )

    with pytest.raises(ConfigError, match=match):
        load_worker_settings(path)
