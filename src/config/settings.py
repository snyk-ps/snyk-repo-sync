"""Unified worker configuration loaded from YAML with optional env overrides."""

import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

import yaml

from config.ado_settings import AdoSettings, parse_ado_settings, require_ado_pat
from config.errors import ConfigError
from config.scope_mapping import ScopeMappingSettings, parse_scope_mapping
from config.snyk_settings import SnykSettings, parse_snyk_settings

DEFAULT_CONFIG_PATH = "data/config.yaml"
DEFAULT_TABLE_NAME = "SnykSyncState"
SNYK_TOKEN_ENV = "SNYK_TOKEN"

SERVICEBUS_FQN_ENV = "SERVICEBUS_FULLY_QUALIFIED_NAMESPACE"
SERVICEBUS_QUEUE_ENV = "SERVICEBUS_QUEUE_NAME"
SYNC_STATE_ENDPOINT_ENV = "SYNC_STATE_STORAGE_ACCOUNT_ENDPOINT"
SYNC_STATE_TABLE_ENV = "SYNC_STATE_TABLE_NAME"


@dataclass(frozen=True)
class ServiceBusSettings:
    """Service Bus namespace and queue reference."""

    fully_qualified_namespace: str
    queue_name: str


@dataclass(frozen=True)
class SyncStateSettings:
    """Azure Table Storage sync-state settings."""

    storage_account_endpoint: str
    table_name: str


@dataclass(frozen=True)
class WorkerSettings:
    """Combined worker configuration."""

    service_bus: ServiceBusSettings
    sync_state: SyncStateSettings
    ado: AdoSettings
    scope_mapping: ScopeMappingSettings
    snyk: SnykSettings


def _require_non_empty(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ConfigError(f"Missing or invalid required setting: {label}")
    return value.strip()


def load_worker_settings(
    config_path: str = DEFAULT_CONFIG_PATH,
    environ: Mapping[str, str] | None = None,
) -> WorkerSettings:
    """Load worker settings from YAML merged with environment overrides.

    Environment variables take precedence over config file values.

    Args:
        config_path: Path to operator config YAML.
        environ: Optional environment mapping for testing.

    Returns:
        Validated worker settings.

    Raises:
        ConfigError: If the config file is missing, invalid, or incomplete.
    """
    path = Path(config_path)
    if not path.is_file():
        raise ConfigError(f"Config file not found: {config_path}")

    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ConfigError(f"Invalid YAML in config file {config_path}: {exc}") from exc

    if not isinstance(raw, dict):
        raise ConfigError(f"Config file must contain a YAML mapping: {config_path}")

    env = os.environ if environ is None else environ
    service_bus_raw = raw.get("serviceBus") or {}
    sync_state_raw = raw.get("syncState") or {}

    if not isinstance(service_bus_raw, dict):
        raise ConfigError("serviceBus must be a mapping")
    if not isinstance(sync_state_raw, dict):
        raise ConfigError("syncState must be a mapping")

    fqn = env.get(SERVICEBUS_FQN_ENV, service_bus_raw.get("fullyQualifiedNamespace"))
    queue_name = env.get(SERVICEBUS_QUEUE_ENV, service_bus_raw.get("queueName"))
    endpoint = env.get(
        SYNC_STATE_ENDPOINT_ENV,
        sync_state_raw.get("storageAccountEndpoint"),
    )
    table_name = env.get(SYNC_STATE_TABLE_ENV, sync_state_raw.get("tableName"))

    resolved_table_name = table_name.strip() if isinstance(table_name, str) and table_name.strip() else DEFAULT_TABLE_NAME
    scope_mapping = parse_scope_mapping(raw.get("scopeMapping"))
    snyk = parse_snyk_settings(raw.get("snyk"))
    ado = parse_ado_settings(raw.get("ado"), env)

    return WorkerSettings(
        service_bus=ServiceBusSettings(
            fully_qualified_namespace=_require_non_empty(
                fqn,
                f"serviceBus.fullyQualifiedNamespace or {SERVICEBUS_FQN_ENV}",
            ),
            queue_name=_require_non_empty(
                queue_name,
                f"serviceBus.queueName or {SERVICEBUS_QUEUE_ENV}",
            ),
        ),
        sync_state=SyncStateSettings(
            storage_account_endpoint=_require_non_empty(
                endpoint,
                f"syncState.storageAccountEndpoint or {SYNC_STATE_ENDPOINT_ENV}",
            ),
            table_name=resolved_table_name,
        ),
        ado=ado,
        scope_mapping=scope_mapping,
        snyk=snyk,
    )


def require_snyk_token(environ: Mapping[str, str] | None = None) -> str:
    """Return the Snyk API token from the environment.

    Raises:
        ConfigError: When ``SNYK_TOKEN`` is missing or empty.
    """
    env = os.environ if environ is None else environ
    token = env.get(SNYK_TOKEN_ENV)
    if not isinstance(token, str) or not token.strip():
        raise ConfigError(f"Missing or empty required environment variable: {SNYK_TOKEN_ENV}")
    return token.strip()
