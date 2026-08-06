"""Tests for worker CLI commands."""

from unittest.mock import patch

from main import build_parser, main


def test_parser_includes_worker_run() -> None:
    parser = build_parser()
    args = parser.parse_args(["worker", "run"])
    assert args.command == "worker"
    assert args.worker_command == "run"
    assert args.func.__name__ == "run_worker"


def test_main_prints_help_without_command() -> None:
    assert main([]) == 0


@patch("commands.worker.WorkerConsumer")
@patch("commands.worker.load_service_bus_settings")
def test_run_worker_starts_consumer(load_settings, consumer_cls) -> None:
    load_settings.return_value = object()
    consumer = consumer_cls.return_value
    consumer.run.side_effect = KeyboardInterrupt

    parser = build_parser()
    args = parser.parse_args(["worker", "run"])
    assert args.func(args) == 0
    consumer.run.assert_called_once()


@patch("commands.worker.load_service_bus_settings")
def test_run_worker_exits_on_missing_config(load_settings) -> None:
    from config.service_bus import ServiceBusConfigError

    load_settings.side_effect = ServiceBusConfigError("missing")

    parser = build_parser()
    args = parser.parse_args(["worker", "run"])
    assert args.func(args) == 1
