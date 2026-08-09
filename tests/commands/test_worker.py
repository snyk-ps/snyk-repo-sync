"""Tests for worker CLI commands."""

import logging
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


@patch("commands.worker.WorkerConsumer")
@patch("commands.worker.SyncStateStore")
@patch("commands.worker.load_worker_settings")
@patch("commands.worker.DefaultAzureCredential")
def test_run_worker_starts_consumer(
    _credential_cls,
    load_settings,
    sync_state_cls,
    consumer_cls,
) -> None:
    from config.scope_mapping import ScopeMappingSettings
    from config.settings import ServiceBusSettings, SyncStateSettings, WorkerSettings

    load_settings.return_value = WorkerSettings(
        service_bus=ServiceBusSettings(
            fully_qualified_namespace="example.servicebus.windows.net",
            queue_name="repo-sync-events",
        ),
        sync_state=SyncStateSettings(
            storage_account_endpoint="https://example.table.core.windows.net",
            table_name="SnykSyncState",
        ),
        scope_mapping=ScopeMappingSettings.empty(),
    )
    sync_state = sync_state_cls.return_value
    consumer = consumer_cls.return_value
    consumer.run.side_effect = KeyboardInterrupt

    parser = build_parser()
    args = parser.parse_args(["worker", "run"])
    assert args.func(args) == 0
    sync_state.ensure_table.assert_called_once()
    consumer.run.assert_called_once()


@patch("commands.worker.load_worker_settings")
def test_run_worker_exits_on_missing_config(load_settings) -> None:
    from config.settings import ConfigError

    load_settings.side_effect = ConfigError("missing")

    parser = build_parser()
    args = parser.parse_args(["worker", "run"])
    assert args.func(args) == 1
