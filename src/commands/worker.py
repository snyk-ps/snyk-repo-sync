"""Worker CLI subcommands."""

import argparse
import logging
import sys

from config.service_bus import ServiceBusConfigError, load_service_bus_settings
from worker.consumer import WorkerConsumer

logger = logging.getLogger(__name__)


def configure_logging() -> None:
    """Configure structured-friendly logging without secrets."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(levelname)s %(name)s %(message)s",
    )


def run_worker(_args: argparse.Namespace) -> int:
    """Start the queue consumer."""
    configure_logging()
    try:
        settings = load_service_bus_settings()
    except ServiceBusConfigError as exc:
        logger.error("%s", exc)
        return 1

    consumer = WorkerConsumer(settings)
    try:
        consumer.run()
    except KeyboardInterrupt:
        logger.info("Worker stopped")
    return 0


def register_worker_commands(subparsers: argparse._SubParsersAction) -> None:
    """Register worker subcommands on the root parser."""
    worker_parser = subparsers.add_parser("worker", help="Worker commands")
    worker_subparsers = worker_parser.add_subparsers(dest="worker_command")

    run_parser = worker_subparsers.add_parser(
        "run",
        help="Consume transport messages from the Service Bus queue",
    )
    run_parser.set_defaults(func=run_worker)
