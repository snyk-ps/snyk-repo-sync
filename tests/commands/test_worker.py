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


@patch("commands.worker.WorkerConsumer")
@patch("commands.worker.DefaultAzureCredential")
@patch("commands.worker.load_worker_settings")
def test_run_worker_kafka_exits_before_service_bus(
    load_settings,
    credential_cls,
    consumer_cls,
) -> None:
    from config.settings import StorageQueueSettings
    from tests.conftest import make_worker_settings

    load_settings.return_value = make_worker_settings(
        transport="kafka",
        service_bus=None,
        storage_queue=StorageQueueSettings(
            queue_service_url="https://example.queue.core.windows.net",
            queue_name="repo-sync-followups",
            poison_queue_name="repo-sync-followups-poison",
        ),
    )

    parser = build_parser()
    args = parser.parse_args(["worker", "run"])
    assert args.func(args) == 1
    credential_cls.assert_not_called()
    consumer_cls.assert_not_called()


@patch("commands.worker.load_worker_settings")
def test_run_worker_exits_on_missing_config(load_settings) -> None:
    from config.settings import ConfigError

    load_settings.side_effect = ConfigError("missing")

    parser = build_parser()
    args = parser.parse_args(["worker", "run"])
    assert args.func(args) == 1
