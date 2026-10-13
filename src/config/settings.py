"""Unified worker configuration loaded from YAML with optional env overrides."""

import os
import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Literal
from urllib.parse import urlparse, urlunparse

import yaml

from config.ado_settings import AdoSettings, parse_ado_settings, require_ado_pat
from config.errors import ConfigError
from config.ignored_repos import IgnoredReposSettings, parse_ignored_repos_settings
from config.scope_mapping import ScopeMappingSettings, parse_scope_mapping
from config.snyk_settings import SnykSettings, parse_snyk_settings

DEFAULT_CONFIG_PATH = "data/config.yaml"
DEFAULT_TABLE_NAME = "SnykSyncState"
SNYK_TOKEN_ENV = "SNYK_TOKEN"

SERVICEBUS_FQN_ENV = "SERVICEBUS_FULLY_QUALIFIED_NAMESPACE"
SERVICEBUS_QUEUE_ENV = "SERVICEBUS_QUEUE_NAME"
SERVICEBUS_RECEIVE_MAX_WAIT_SECONDS_ENV = "SERVICEBUS_RECEIVE_MAX_WAIT_SECONDS"
SYNC_STATE_ENDPOINT_ENV = "SYNC_STATE_STORAGE_ACCOUNT_ENDPOINT"
SYNC_STATE_TABLE_ENV = "SYNC_STATE_TABLE_NAME"
MESSAGING_TRANSPORT_ENV = "MESSAGING_TRANSPORT"
STORAGE_QUEUE_NAME_ENV = "STORAGE_QUEUE_NAME"
STORAGE_QUEUE_POISON_NAME_ENV = "STORAGE_QUEUE_POISON_NAME"
STORAGE_QUEUE_RECEIVE_MAX_WAIT_SECONDS_ENV = "STORAGE_QUEUE_RECEIVE_MAX_WAIT_SECONDS"
STORAGE_QUEUE_VISIBILITY_TIMEOUT_SECONDS_ENV = "STORAGE_QUEUE_VISIBILITY_TIMEOUT_SECONDS"

DEFAULT_RECEIVE_MAX_WAIT_SECONDS = 5
MAX_RECEIVE_MAX_WAIT_SECONDS = 300
DEFAULT_VISIBILITY_TIMEOUT_SECONDS = 60
MAX_VISIBILITY_TIMEOUT_SECONDS = 604800

MessageTransport = Literal["serviceBus", "kafka"]
EVENT_CONNECTOR_PENDING_MESSAGE = (
    "GitHub event connector is not implemented; "
    "the event-connector REST API contract is pending"
)

_QUEUE_NAME_RE = re.compile(r"^[a-z0-9](?:[a-z0-9]|-(?!-)){1,61}[a-z0-9]$")


@dataclass(frozen=True)
class ServiceBusSettings:
    """Service Bus namespace and queue reference."""

    fully_qualified_namespace: str
    queue_name: str
    receive_max_wait_seconds: int = DEFAULT_RECEIVE_MAX_WAIT_SECONDS


@dataclass(frozen=True)
class SyncStateSettings:
    """Azure Table Storage sync-state settings."""

    storage_account_endpoint: str
    table_name: str


@dataclass(frozen=True)
class StorageQueueSettings:
    """Azure Storage queue for worker follow-up messages on the kafka transport."""

    queue_service_url: str
    queue_name: str
    poison_queue_name: str
    receive_max_wait_seconds: int = DEFAULT_RECEIVE_MAX_WAIT_SECONDS
    visibility_timeout_seconds: int = DEFAULT_VISIBILITY_TIMEOUT_SECONDS


@dataclass(frozen=True)
class WorkerSettings:
    """Combined worker configuration."""

    service_bus: ServiceBusSettings | None
    sync_state: SyncStateSettings
    ado: AdoSettings
    scope_mapping: ScopeMappingSettings
    snyk: SnykSettings
    ignored_repos: IgnoredReposSettings | None = None
    transport: MessageTransport = "serviceBus"
    storage_queue: StorageQueueSettings | None = None


def _require_non_empty(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ConfigError(f"Missing or invalid required setting: {label}")
    return value.strip()


def _parse_bounded_int(
    value: object,
    *,
    label: str,
    minimum: int,
    maximum: int,
    default: int,
) -> int:
    if value is None:
        return default
    if isinstance(value, bool):
        raise ConfigError(f"Missing or invalid required setting: {label}")
    if isinstance(value, int):
        parsed = value
    elif isinstance(value, str) and value.strip().isdigit():
        parsed = int(value.strip())
    else:
        raise ConfigError(f"Missing or invalid required setting: {label}")
    if parsed < minimum or parsed > maximum:
        raise ConfigError(
            f"{label} must be an integer between {minimum} and {maximum}, got {parsed!r}"
        )
    return parsed


def _parse_receive_max_wait_seconds(value: object, *, label: str) -> int:
    return _parse_bounded_int(
        value,
        label=label,
        minimum=1,
        maximum=MAX_RECEIVE_MAX_WAIT_SECONDS,
        default=DEFAULT_RECEIVE_MAX_WAIT_SECONDS,
    )


def _parse_transport(value: object) -> MessageTransport:
    if value is None:
        return "serviceBus"
    if value == "serviceBus" or value == "kafka":
        return value
    raise ConfigError(
        f"Missing or invalid required setting: messaging.transport or {MESSAGING_TRANSPORT_ENV}"
    )


def _validate_queue_name(value: str, *, label: str) -> str:
    if _QUEUE_NAME_RE.fullmatch(value) is None:
        raise ConfigError(
            f"{label} must be 3-63 characters of lowercase letters, numbers, and hyphens, "
            f"must start and end with a letter or number, and must not contain consecutive hyphens, "
            f"got {value!r}"
        )
    return value


def derive_queue_service_url(table_endpoint: str) -> str:
    """Return the queue service URL for the storage account that hosts the table.

    Replaces the ``.table.`` host label with ``.queue.``.

    Raises:
        ConfigError: When the endpoint is not a table service URL.
    """
    parsed = urlparse(table_endpoint.strip())
    host = parsed.hostname
    if parsed.scheme not in {"https", "http"} or not host or ".table." not in host:
        raise ConfigError(
            "syncState.storageAccountEndpoint must be a table service URL "
            "containing a .table. host label so the queue endpoint can be derived, "
            f"got {table_endpoint!r}"
        )
    queue_host = host.replace(".table.", ".queue.", 1)
    netloc = queue_host if parsed.port is None else f"{queue_host}:{parsed.port}"
    return urlunparse((parsed.scheme, netloc, "", "", "", ""))


def _parse_service_bus_settings(
    service_bus_raw: Mapping[str, object],
    env: Mapping[str, str],
) -> ServiceBusSettings:
    receive_max_wait_seconds = _parse_receive_max_wait_seconds(
        env.get(
            SERVICEBUS_RECEIVE_MAX_WAIT_SECONDS_ENV,
            service_bus_raw.get("receiveMaxWaitSeconds"),
        ),
        label=f"serviceBus.receiveMaxWaitSeconds or {SERVICEBUS_RECEIVE_MAX_WAIT_SECONDS_ENV}",
    )
    return ServiceBusSettings(
        fully_qualified_namespace=_require_non_empty(
            env.get(SERVICEBUS_FQN_ENV, service_bus_raw.get("fullyQualifiedNamespace")),
            f"serviceBus.fullyQualifiedNamespace or {SERVICEBUS_FQN_ENV}",
        ),
        queue_name=_require_non_empty(
            env.get(SERVICEBUS_QUEUE_ENV, service_bus_raw.get("queueName")),
            f"serviceBus.queueName or {SERVICEBUS_QUEUE_ENV}",
        ),
        receive_max_wait_seconds=receive_max_wait_seconds,
    )


def _parse_storage_queue_settings(
    storage_queue_raw: Mapping[str, object],
    env: Mapping[str, str],
    table_endpoint: str,
) -> StorageQueueSettings:
    queue_name = _validate_queue_name(
        _require_non_empty(
            env.get(STORAGE_QUEUE_NAME_ENV, storage_queue_raw.get("queueName")),
            f"storageQueue.queueName or {STORAGE_QUEUE_NAME_ENV}",
        ),
        label=f"storageQueue.queueName or {STORAGE_QUEUE_NAME_ENV}",
    )
    poison_raw = env.get(STORAGE_QUEUE_POISON_NAME_ENV, storage_queue_raw.get("poisonQueueName"))
    if poison_raw is None or (isinstance(poison_raw, str) and not poison_raw.strip()):
        poison_name = f"{queue_name}-poison"
    else:
        poison_name = poison_raw.strip() if isinstance(poison_raw, str) else str(poison_raw)
    poison_queue_name = _validate_queue_name(
        poison_name,
        label=f"storageQueue.poisonQueueName or {STORAGE_QUEUE_POISON_NAME_ENV}",
    )
    receive_max_wait_seconds = _parse_receive_max_wait_seconds(
        env.get(
            STORAGE_QUEUE_RECEIVE_MAX_WAIT_SECONDS_ENV,
            storage_queue_raw.get("receiveMaxWaitSeconds"),
        ),
        label=(
            "storageQueue.receiveMaxWaitSeconds or "
            f"{STORAGE_QUEUE_RECEIVE_MAX_WAIT_SECONDS_ENV}"
        ),
    )
    visibility_timeout_seconds = _parse_bounded_int(
        env.get(
            STORAGE_QUEUE_VISIBILITY_TIMEOUT_SECONDS_ENV,
            storage_queue_raw.get("visibilityTimeoutSeconds"),
        ),
        label=(
            "storageQueue.visibilityTimeoutSeconds or "
            f"{STORAGE_QUEUE_VISIBILITY_TIMEOUT_SECONDS_ENV}"
        ),
        minimum=1,
        maximum=MAX_VISIBILITY_TIMEOUT_SECONDS,
        default=DEFAULT_VISIBILITY_TIMEOUT_SECONDS,
    )
    return StorageQueueSettings(
        queue_service_url=derive_queue_service_url(table_endpoint),
        queue_name=queue_name,
        poison_queue_name=poison_queue_name,
        receive_max_wait_seconds=receive_max_wait_seconds,
        visibility_timeout_seconds=visibility_timeout_seconds,
    )


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
    messaging_raw = raw.get("messaging") or {}
    service_bus_raw = raw.get("serviceBus") or {}
    sync_state_raw = raw.get("syncState") or {}
    storage_queue_raw = raw.get("storageQueue") or {}

    if not isinstance(messaging_raw, dict):
        raise ConfigError("messaging must be a mapping")
    if not isinstance(service_bus_raw, dict):
        raise ConfigError("serviceBus must be a mapping")
    if not isinstance(sync_state_raw, dict):
        raise ConfigError("syncState must be a mapping")
    if not isinstance(storage_queue_raw, dict):
        raise ConfigError("storageQueue must be a mapping")

    transport = _parse_transport(env.get(MESSAGING_TRANSPORT_ENV, messaging_raw.get("transport")))
    endpoint = _require_non_empty(
        env.get(SYNC_STATE_ENDPOINT_ENV, sync_state_raw.get("storageAccountEndpoint")),
        f"syncState.storageAccountEndpoint or {SYNC_STATE_ENDPOINT_ENV}",
    )
    table_name = env.get(SYNC_STATE_TABLE_ENV, sync_state_raw.get("tableName"))
    resolved_table_name = (
        table_name.strip() if isinstance(table_name, str) and table_name.strip() else DEFAULT_TABLE_NAME
    )
    scope_mapping = parse_scope_mapping(raw.get("scopeMapping"))
    snyk = parse_snyk_settings(raw.get("snyk"))
    ado = parse_ado_settings(raw.get("ado"), env)
    ignored_repos = parse_ignored_repos_settings(raw.get("ignoredRepos"), config_path=path)

    service_bus: ServiceBusSettings | None = None
    storage_queue: StorageQueueSettings | None = None
    if transport == "serviceBus":
        service_bus = _parse_service_bus_settings(service_bus_raw, env)
    else:
        storage_queue = _parse_storage_queue_settings(storage_queue_raw, env, endpoint)

    return WorkerSettings(
        service_bus=service_bus,
        sync_state=SyncStateSettings(
            storage_account_endpoint=endpoint,
            table_name=resolved_table_name,
        ),
        ado=ado,
        scope_mapping=scope_mapping,
        snyk=snyk,
        ignored_repos=ignored_repos,
        transport=transport,
        storage_queue=storage_queue,
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
