"""Tests for unified worker configuration."""

from pathlib import Path

import pytest
import yaml

from config.settings import (
    DEFAULT_TABLE_NAME,
    SERVICEBUS_FQN_ENV,
    SERVICEBUS_QUEUE_ENV,
    SYNC_STATE_ENDPOINT_ENV,
    SYNC_STATE_TABLE_ENV,
    ConfigError,
    load_worker_settings,
)


def _write_config(tmp_path: Path, data: dict) -> str:
    path = tmp_path / "config.yaml"
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
    assert settings.sync_state.storage_account_endpoint == "https://example.table.core.windows.net"
    assert settings.sync_state.table_name == DEFAULT_TABLE_NAME


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
