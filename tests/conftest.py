"""Shared test helpers for worker settings."""

from config.ado_settings import AdoSettings
from config.scope_mapping import ScopeMappingSettings
from config.settings import ServiceBusSettings, SyncStateSettings, WorkerSettings
from config.snyk_settings import SnykSettings, TargetRemovalSettings


def make_worker_settings(**overrides) -> WorkerSettings:
    """Build worker settings with sensible defaults for tests."""
    defaults = WorkerSettings(
        service_bus=ServiceBusSettings(
            fully_qualified_namespace="example.servicebus.windows.net",
            queue_name="repo-sync-events",
        ),
        sync_state=SyncStateSettings(
            storage_account_endpoint="https://example.table.core.windows.net",
            table_name="SnykSyncState",
        ),
        ado=AdoSettings(organization="example-org"),
        scope_mapping=ScopeMappingSettings.empty(),
        snyk=SnykSettings(
            max_concurrent_pending_imports=100,
            target_removal=TargetRemovalSettings(
                on_rename="deactivate",
                on_default_branch_change="deactivate",
                on_repo_delete="deactivate",
                on_ignore="deactivate",
            ),
        ),
    )
    if not overrides:
        return defaults
    return WorkerSettings(
        service_bus=overrides.get("service_bus", defaults.service_bus),
        sync_state=overrides.get("sync_state", defaults.sync_state),
        ado=overrides.get("ado", defaults.ado),
        scope_mapping=overrides.get("scope_mapping", defaults.scope_mapping),
        snyk=overrides.get("snyk", defaults.snyk),
    )
