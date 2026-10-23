"""Tests for worker CLI commands."""

import logging
from pathlib import Path
from unittest.mock import patch

from commands.worker import configure_logging
from config.settings import DEFAULT_CONFIG_PATH
from main import build_parser, main


def test_configure_logging_suppresses_noisy_sdk_loggers() -> None:
    configure_logging()

    assert logging.getLogger().level == logging.INFO
    assert logging.getLogger("worker.consumer").getEffectiveLevel() == logging.INFO
    assert logging.getLogger("azure.servicebus").level == logging.WARNING
    assert logging.getLogger("azure").level == logging.WARNING
    assert logging.getLogger("azure.identity").level == logging.WARNING
    assert logging.getLogger("uamqp").level == logging.WARNING


def test_parser_includes_worker_run_with_default_config() -> None:
    parser = build_parser()
    args = parser.parse_args(["worker", "run"])
    assert args.command == "worker"
    assert args.worker_command == "run"
    assert args.config == DEFAULT_CONFIG_PATH
    assert args.func.__name__ == "run_worker"


def test_parser_accepts_custom_config_path() -> None:
    parser = build_parser()
    args = parser.parse_args(["worker", "run", "--config", "/config/config.yaml"])
    assert args.config == "/config/config.yaml"


def test_main_prints_help_without_command() -> None:
    assert main([]) == 0


@patch("commands.worker.UvicornHttpServer")
@patch("commands.worker.GitHubEventsApp")
@patch("commands.worker.AdoClient")
@patch("commands.worker.require_ado_pat", return_value="test-ado-pat")
@patch("commands.worker.require_snyk_token", return_value="test-token")
@patch("commands.worker.WorkerConsumer")
@patch("commands.worker.SyncStateStore")
@patch("commands.worker.load_worker_settings")
@patch("commands.worker.DefaultAzureCredential")
def test_run_worker_starts_consumer(
    _credential_cls,
    load_settings,
    sync_state_cls,
    consumer_cls,
    _require_token,
    require_ado_pat,
    ado_client_cls,
    app_cls,
    server_cls,
) -> None:
    from config.ado_settings import AdoSettings
    from config.scope_mapping import parse_scope_mapping
    from tests.conftest import make_worker_settings

    load_settings.return_value = make_worker_settings(
        ado=AdoSettings(organization="example-org"),
        scope_mapping=parse_scope_mapping(
            {
                "azure-repos": [
                    {"projectName": "proj", "snykOrgId": "org"},
                ],
            },
        ),
    )
    sync_state = sync_state_cls.return_value
    consumer = consumer_cls.return_value
    consumer.run.side_effect = KeyboardInterrupt

    parser = build_parser()
    args = parser.parse_args(["worker", "run"])
    assert args.func(args) == 0
    sync_state.ensure_table.assert_called_once()
    consumer.run.assert_called_once()
    require_ado_pat.assert_called_once_with()
    ado_client_cls.assert_called_once_with(
        "test-ado-pat",
        organization="example-org",
        host="dev.azure.com",
    )
    app_cls.assert_not_called()
    server_cls.assert_not_called()


@patch("commands.worker.AdoClient")
@patch("commands.worker.require_ado_pat")
@patch("commands.worker.require_snyk_token", return_value="test-token")
@patch("commands.worker.WorkerConsumer")
@patch("commands.worker.SyncStateStore")
@patch("commands.worker.load_worker_settings")
@patch("commands.worker.DefaultAzureCredential")
def test_run_worker_without_ado_mapping_skips_ado_credentials(
    _credential_cls,
    load_settings,
    sync_state_cls,
    consumer_cls,
    _require_token,
    require_ado_pat,
    ado_client_cls,
) -> None:
    from tests.conftest import make_worker_settings

    load_settings.return_value = make_worker_settings()
    consumer = consumer_cls.return_value
    consumer.run.side_effect = KeyboardInterrupt

    parser = build_parser()
    args = parser.parse_args(["worker", "run"])

    assert args.func(args) == 0
    sync_state_cls.return_value.ensure_table.assert_called_once()
    require_ado_pat.assert_not_called()
    ado_client_cls.assert_not_called()


@patch("commands.worker.IgnoreReconciliationLoop")
@patch("commands.worker.IgnorePolicyState")
@patch("commands.worker.require_snyk_token", return_value="test-token")
@patch("commands.worker.KafkaRuntime")
@patch("commands.worker.UvicornHttpServer")
@patch("commands.worker.GitHubEventsApp")
@patch("commands.worker.open_storage_queue_transport")
@patch("commands.worker.WorkerConsumer")
@patch("commands.worker.SyncStateStore")
@patch("commands.worker.DefaultAzureCredential")
@patch("commands.worker.load_worker_settings")
def test_run_worker_kafka_starts_http_and_storage_queue_without_service_bus(
    load_settings,
    _credential_cls,
    sync_state_cls,
    consumer_cls,
    open_storage_queue,
    app_cls,
    server_cls,
    runtime_cls,
    _require_token,
    policy_state_cls,
    reconciliation_cls,
) -> None:
    from config.ignored_repos import IgnoredReposSettings
    from config.settings import HttpSettings, StorageQueueSettings
    from tests.conftest import make_worker_settings

    storage_settings = StorageQueueSettings(
        queue_service_url="https://example.queue.core.windows.net",
        queue_name="repo-sync-followups",
        poison_queue_name="repo-sync-followups-poison",
    )
    http_settings = HttpSettings()
    load_settings.return_value = make_worker_settings(
        transport="kafka",
        service_bus=None,
        storage_queue=storage_settings,
        http=http_settings,
        ignored_repos=IgnoredReposSettings(
            policy_path=Path("ignored-repos.yaml"),
            reconciliation_interval_minutes=15,
        ),
    )
    runtime_cls.return_value.run.side_effect = KeyboardInterrupt

    parser = build_parser()
    args = parser.parse_args(["worker", "run"])
    assert args.func(args) == 0
    sync_state_cls.return_value.ensure_table.assert_called_once_with()
    consumer_cls.assert_not_called()
    open_storage_queue.assert_called_once()
    app_cls.assert_called_once()
    server_cls.assert_called_once()
    runtime_cls.return_value.run.assert_called_once_with()
    policy_state_cls.return_value.load_from_file.assert_called_once()
    reconciliation_cls.return_value.start.assert_called_once_with()
    reconciliation_cls.return_value.stop.assert_called_once_with()


@patch("commands.worker.load_worker_settings")
def test_run_worker_exits_on_missing_config(load_settings) -> None:
    from config.settings import ConfigError

    load_settings.side_effect = ConfigError("missing")

    parser = build_parser()
    args = parser.parse_args(["worker", "run"])
    assert args.func(args) == 1
