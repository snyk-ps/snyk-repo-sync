"""Tests for unified worker configuration."""

from pathlib import Path

import pytest
import yaml

from config.settings import (
    DEFAULT_TABLE_NAME,
    MESSAGING_TRANSPORT_ENV,
    SERVICEBUS_FQN_ENV,
    SERVICEBUS_QUEUE_ENV,
    SERVICEBUS_RECEIVE_MAX_WAIT_SECONDS_ENV,
    SNYK_TOKEN_ENV,
    STORAGE_QUEUE_NAME_ENV,
    STORAGE_QUEUE_POISON_NAME_ENV,
    STORAGE_QUEUE_RECEIVE_MAX_WAIT_SECONDS_ENV,
    STORAGE_QUEUE_VISIBILITY_TIMEOUT_SECONDS_ENV,
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

    assert settings.transport == "serviceBus"
    assert settings.storage_queue is None
    assert settings.service_bus is not None
    assert settings.service_bus.fully_qualified_namespace == "example.servicebus.windows.net"
    assert settings.service_bus.queue_name == "repo-sync-events"
    assert settings.service_bus.receive_max_wait_seconds == 5
    assert settings.sync_state.storage_account_endpoint == "https://example.table.core.windows.net"
    assert settings.sync_state.table_name == DEFAULT_TABLE_NAME
    assert settings.scope_mapping.default_snyk_org_id is None
    assert settings.scope_mapping.ado_by_project_name == {}
    assert settings.snyk.max_concurrent_pending_imports == 100
    assert settings.ado is None


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
    assert settings.ado is not None
    assert settings.ado.organization == "example-org"


def test_load_worker_settings_without_ado_mapping_ignores_ado_settings(
    tmp_path: Path,
) -> None:
    path = _write_config(
        tmp_path,
        {
            "ado": {},
            "serviceBus": {
                "fullyQualifiedNamespace": "example.servicebus.windows.net",
                "queueName": "repo-sync-events",
            },
            "syncState": {
                "storageAccountEndpoint": "https://example.table.core.windows.net",
            },
            "scopeMapping": {
                "github-cloud-app": [
                    {"orgName": "contoso", "snykOrgId": "github-org"},
                ],
            },
        },
    )

    settings = load_worker_settings(path, {})

    assert settings.ado is None


def test_load_worker_settings_with_ado_mapping_requires_organization(
    tmp_path: Path,
) -> None:
    path = _write_config(
        tmp_path,
        {
            "ado": {},
            "serviceBus": {
                "fullyQualifiedNamespace": "example.servicebus.windows.net",
                "queueName": "repo-sync-events",
            },
            "syncState": {
                "storageAccountEndpoint": "https://example.table.core.windows.net",
            },
            "scopeMapping": {
                "azure-repos": [
                    {"projectName": "proj", "snykOrgId": "ado-org"},
                ],
            },
        },
    )

    with pytest.raises(ConfigError, match="ado.organization"):
        load_worker_settings(path, {})


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

    assert settings.service_bus is not None
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

    assert settings.service_bus is not None
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

    assert settings.service_bus is not None
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


def _kafka_config(**overrides: object) -> dict:
    data: dict = {
        "messaging": {"transport": "kafka"},
        "syncState": {
            "storageAccountEndpoint": "https://example.table.core.windows.net",
        },
        "storageQueue": {"queueName": "repo-sync-followups"},
    }
    data.update(overrides)
    return data


def test_load_worker_settings_kafka_derives_queue_url_without_service_bus(tmp_path: Path) -> None:
    path = _write_config(tmp_path, _kafka_config())

    settings = load_worker_settings(path)

    assert settings.transport == "kafka"
    assert settings.service_bus is None
    assert settings.storage_queue is not None
    assert settings.storage_queue.queue_service_url == "https://example.queue.core.windows.net"
    assert settings.storage_queue.queue_name == "repo-sync-followups"
    assert settings.storage_queue.poison_queue_name == "repo-sync-followups-poison"
    assert settings.storage_queue.receive_max_wait_seconds == 5
    assert settings.storage_queue.visibility_timeout_seconds == 60


def test_load_worker_settings_kafka_env_overrides(tmp_path: Path) -> None:
    path = _write_config(
        tmp_path,
        _kafka_config(
            storageQueue={
                "queueName": "file-queue",
                "poisonQueueName": "file-poison",
                "receiveMaxWaitSeconds": 15,
                "visibilityTimeoutSeconds": 30,
            },
        ),
    )

    settings = load_worker_settings(
        path,
        {
            MESSAGING_TRANSPORT_ENV: "kafka",
            STORAGE_QUEUE_NAME_ENV: "env-queue",
            STORAGE_QUEUE_POISON_NAME_ENV: "env-poison",
            STORAGE_QUEUE_RECEIVE_MAX_WAIT_SECONDS_ENV: "20",
            STORAGE_QUEUE_VISIBILITY_TIMEOUT_SECONDS_ENV: "90",
            SYNC_STATE_ENDPOINT_ENV: "https://gov.table.core.usgovcloudapi.net",
        },
    )

    assert settings.storage_queue is not None
    assert settings.storage_queue.queue_name == "env-queue"
    assert settings.storage_queue.poison_queue_name == "env-poison"
    assert settings.storage_queue.receive_max_wait_seconds == 20
    assert settings.storage_queue.visibility_timeout_seconds == 90
    assert settings.storage_queue.queue_service_url == "https://gov.queue.core.usgovcloudapi.net"


def test_load_worker_settings_rejects_unknown_transport(tmp_path: Path) -> None:
    path = _write_config(tmp_path, _kafka_config(messaging={"transport": "eventHub"}))

    with pytest.raises(ConfigError, match="messaging.transport"):
        load_worker_settings(path)


def test_load_worker_settings_kafka_requires_queue_name(tmp_path: Path) -> None:
    path = _write_config(tmp_path, _kafka_config(storageQueue={}))

    with pytest.raises(ConfigError, match="queueName"):
        load_worker_settings(path)


def test_load_worker_settings_kafka_rejects_non_table_endpoint(tmp_path: Path) -> None:
    path = _write_config(
        tmp_path,
        _kafka_config(
            syncState={"storageAccountEndpoint": "https://example.blob.core.windows.net"},
        ),
    )

    with pytest.raises(ConfigError, match=r"\.table\."):
        load_worker_settings(path)


@pytest.mark.parametrize("queue_name", ["ab", "Repo", "a--b", "-abc", "abc-"])
def test_load_worker_settings_rejects_invalid_queue_name(tmp_path: Path, queue_name: str) -> None:
    path = _write_config(tmp_path, _kafka_config(storageQueue={"queueName": queue_name}))

    with pytest.raises(ConfigError, match="lowercase"):
        load_worker_settings(path)


def test_load_worker_settings_service_bus_ignores_storage_queue_section(tmp_path: Path) -> None:
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
            "storageQueue": {"queueName": "NOT-VALID"},
        },
    )

    settings = load_worker_settings(path)

    assert settings.transport == "serviceBus"
    assert settings.storage_queue is None
