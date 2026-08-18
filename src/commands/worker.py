"""Worker CLI subcommands."""

import argparse
import logging

from azure.identity import DefaultAzureCredential

from ado.client import AdoClient
from config.settings import (
    ConfigError,
    DEFAULT_CONFIG_PATH,
    load_worker_settings,
    require_ado_pat,
    require_snyk_token,
)
from snyk.client import SnykClient
from snyk.integration_resolver import IntegrationResolver
from sync_state import SyncStateStore
from worker.consumer import WorkerConsumer
from worker.ignore_policy import IgnorePolicyState
from worker.lifecycle import WorkerSyncDependencies
from worker.reconciliation import IgnoreReconciliationLoop

logger = logging.getLogger(__name__)

_NOISY_LOGGERS = (
    "azure",
    "azure.servicebus",
    "azure.identity",
    "uamqp",
)


def configure_logging() -> None:
    """Configure structured-friendly logging without secrets."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(levelname)s %(name)s %(message)s",
        force=True,
    )
    for name in _NOISY_LOGGERS:
        logging.getLogger(name).setLevel(logging.WARNING)


def run_worker(args: argparse.Namespace) -> int:
    """Start the queue consumer."""
    configure_logging()
    try:
        settings = load_worker_settings(args.config)
        snyk_token = require_snyk_token()
        ado_pat = require_ado_pat()
    except ConfigError as exc:
        logger.error("%s", exc)
        return 1

    credential = DefaultAzureCredential()
    sync_state = SyncStateStore(settings.sync_state, credential=credential)
    try:
        sync_state.ensure_table()
    except Exception as exc:
        logger.error("Failed to ensure sync-state table: %s", exc)
        return 1

    snyk_client = SnykClient(snyk_token)
    ado_client = AdoClient(
        ado_pat,
        organization=settings.ado.organization,
        host=settings.ado.host,
    )
    policy_state: IgnorePolicyState | None = None
    if settings.ignored_repos is not None:
        policy_state = IgnorePolicyState()
        try:
            policy_state.load_from_file(settings.ignored_repos.policy_path, sync_state)
        except ConfigError as exc:
            logger.error("%s", exc)
            return 1
        logger.info(
            "Ignore policy loaded path=%s reconciliation_interval_minutes=%s",
            settings.ignored_repos.policy_path,
            settings.ignored_repos.reconciliation_interval_minutes,
        )

    sync_deps = WorkerSyncDependencies(
        sync_state=sync_state,
        snyk=snyk_client,
        ado=ado_client,
        integration_resolver=IntegrationResolver(snyk_client),
        scope_mapping=settings.scope_mapping,
        snyk_settings=settings.snyk,
        ignore_policy_state=policy_state,
    )

    reconciliation_loop: IgnoreReconciliationLoop | None = None
    if settings.ignored_repos is not None and policy_state is not None:
        reconciliation_loop = IgnoreReconciliationLoop(
            settings=settings.ignored_repos,
            policy_state=policy_state,
            sync_state=sync_state,
            deps=sync_deps,
        )
        reconciliation_loop.start()

    consumer = WorkerConsumer(settings, sync_state, sync_deps=sync_deps, credential=credential)
    try:
        consumer.run()
    except KeyboardInterrupt:
        logger.info("Worker stopped")
    finally:
        if reconciliation_loop is not None:
            reconciliation_loop.stop()
    return 0


def register_worker_commands(subparsers: argparse._SubParsersAction) -> None:
    """Register worker subcommands on the root parser."""
    worker_parser = subparsers.add_parser("worker", help="Worker commands")
    worker_subparsers = worker_parser.add_subparsers(dest="worker_command")

    run_parser = worker_subparsers.add_parser(
        "run",
        help="Consume queue messages from the Service Bus queue",
    )
    run_parser.add_argument(
        "--config",
        default=DEFAULT_CONFIG_PATH,
        help=f"Operator config file path (default: {DEFAULT_CONFIG_PATH})",
    )
    run_parser.set_defaults(func=run_worker)
