"""Tests for queue message handling."""

import json
from pathlib import Path
from unittest.mock import MagicMock
from unittest.mock import patch

from config.errors import ConfigError
from config.scope_mapping import (
    AdoScopeEntry,
    ResolvedScopeMapping,
    ScopeMappingSettings,
    UnmappedScope,
)
from config.snyk_settings import SnykSettings, TargetRemovalSettings
from snyk.client import SnykApiError
from worker.handler import HandleResult, handle_queue_message, process_message_body
from worker.lifecycle import WorkerSyncDependencies


def _ado_created_body(project_name: str = "proj") -> bytes:
    return json.dumps(
        {
            "subject": "AzureDevOps/Auditing",
            "eventType": "AzureDevOpsAuditEvent",
            "data": {
                "Id": "evt-1",
                "ActionId": "Git.RepositoryCreated",
                "ScopeId": "org",
                "ScopeDisplayName": "org",
                "ProjectId": "proj-id",
                "ProjectName": project_name,
                "Timestamp": "2026-08-07T17:50:45.8246565Z",
                "Data": {"RepoId": "repo", "RepoName": "demo"},
            },
        }
    ).encode("utf-8")


def test_handle_default_branch_changed_without_previous_branch_completes(caplog) -> None:
    body = json.dumps(
        {
            "id": "911fef54-3e24-4c7a-bdf0-84679380b4c7",
            "subject": "AzureDevOps/Auditing",
            "eventType": "AzureDevOpsAuditEvent",
            "data": {
                "Id": "911fef54-3e24-4c7a-bdf0-84679380b4c7",
                "ActionId": "Git.RepositoryDefaultBranchChanged",
                "ScopeId": "c638432a-7f35-450f-984f-372b9d46a376",
                "ScopeDisplayName": "torstencannell (Organization)",
                "ProjectId": "da9734d4-a91a-4f03-814b-ecc721fe24d1",
                "ProjectName": "snykDemoProject",
                "Timestamp": "2026-08-07T17:50:45.8246565Z",
                "Data": {
                    "RepoId": "28b62628-73ec-4f6b-89cb-d5a023e9be23",
                    "RepoName": "test-repo",
                    "DefaultBranch": "refs/heads/main",
                    "PreviousDefaultBranch": "",
                },
            },
        }
    ).encode("utf-8")

    with caplog.at_level("INFO"):
        result = handle_queue_message(body)

    assert result.normalized is not None
    assert result.normalized.payload == {"defaultBranch": "main"}
    assert isinstance(result.scope_resolution, UnmappedScope)
    assert "no sync action needed" in caplog.text
    assert "Normalized ADO lifecycle event" not in caplog.text


def test_handle_ado_created_normalizes_and_returns_event() -> None:
    result = handle_queue_message(_ado_created_body())

    assert result.normalized is not None
    assert result.normalized.event_type == "repo.created"
    assert isinstance(result.scope_resolution, UnmappedScope)


def test_handle_ado_created_resolves_mapped_scope(caplog) -> None:
    mapping = ScopeMappingSettings(
        default_snyk_org_id=None,
        ado_by_project_name={
            "proj": AdoScopeEntry(
                snyk_org_id="mapped-org",
                integration_type="azure-repos",
                source="ado",
            ),
        },
        github_by_org_name={},
        configured_github_integration_types=frozenset(),
    )

    with caplog.at_level("INFO"):
        result = handle_queue_message(_ado_created_body(), scope_mapping=mapping)

    assert isinstance(result.scope_resolution, ResolvedScopeMapping)
    assert result.scope_resolution.snyk_org_id == "mapped-org"
    assert "Resolved scope mapping" in caplog.text
    assert "mapped-org" in caplog.text


def test_handle_ado_created_uses_default_org(caplog) -> None:
    mapping = ScopeMappingSettings(
        default_snyk_org_id="default-org",
        ado_by_project_name={},
        github_by_org_name={},
        configured_github_integration_types=frozenset(),
    )

    with caplog.at_level("INFO"):
        result = handle_queue_message(_ado_created_body("other-project"), scope_mapping=mapping)

    assert isinstance(result.scope_resolution, ResolvedScopeMapping)
    assert result.scope_resolution.resolution == "default"
    assert result.scope_resolution.snyk_org_id == "default-org"
    assert "default-org" in caplog.text


def test_handle_ado_created_logs_unmapped_scope(caplog) -> None:
    with caplog.at_level("WARNING"):
        result = handle_queue_message(_ado_created_body("missing-project"))

    assert isinstance(result.scope_resolution, UnmappedScope)
    assert "scope_mapping_unmapped" in caplog.text


def test_handle_github_message_normalizes_and_resolves_unmapped_scope() -> None:
    body = json.dumps(
        {
            "action": "created",
            "repository": {
                "id": 1,
                "name": "demo",
                "full_name": "sample-org/demo",
                "default_branch": "main",
                "updated_at": "2026-10-01T12:00:00Z",
                "owner": {"login": "sample-org", "type": "Organization"},
            },
        }
    ).encode("utf-8")

    result = handle_queue_message(body)

    assert result.normalized is not None
    assert result.normalized.source == "github"
    assert isinstance(result.scope_resolution, UnmappedScope)


def _sync_deps() -> WorkerSyncDependencies:
    sync_state = MagicMock()
    sync_state.get_repository.return_value = None
    sync_state.count_pending_imports.return_value = 0
    snyk = MagicMock()
    snyk.start_import.return_value = "job-1"
    integration_resolver = MagicMock()
    integration_resolver.resolve.return_value = "integration-1"
    ado = MagicMock()
    return WorkerSyncDependencies(
        sync_state=sync_state,
        snyk=snyk,
        ado=ado,
        integration_resolver=integration_resolver,
        scope_mapping=ScopeMappingSettings(
            default_snyk_org_id=None,
            ado_by_project_name={
                "proj": AdoScopeEntry(
                    snyk_org_id="mapped-org",
                    integration_type="azure-repos",
                    source="ado",
                ),
            },
            github_by_org_name={},
            configured_github_integration_types=frozenset(),
        ),
        snyk_settings=SnykSettings(
            max_concurrent_pending_imports=100,
            target_removal=TargetRemovalSettings(
                on_rename="deactivate",
                on_default_branch_change="deactivate",
                on_repo_delete="deactivate",
                on_ignore="deactivate",
            ),
        ),
    )


def test_handle_ado_created_with_sync_deps_schedules_import_poll() -> None:
    mapping = ScopeMappingSettings(
        default_snyk_org_id=None,
        ado_by_project_name={
            "proj": AdoScopeEntry(
                snyk_org_id="mapped-org",
                integration_type="azure-repos",
                source="ado",
            ),
        },
        github_by_org_name={},
        configured_github_integration_types=frozenset(),
    )
    result = handle_queue_message(
        _ado_created_body(),
        scope_mapping=mapping,
        sync_deps=_sync_deps(),
    )

    assert result.settlement == "complete"
    assert len(result.scheduled_followups) == 1
    assert result.scheduled_followups[0].body["syncPhase"] == "import_poll"


def test_process_message_body_returns_completed_for_unmapped_scope() -> None:
    outcome = process_message_body(_ado_created_body())

    assert outcome.status == "completed"
    assert outcome.result is not None
    assert isinstance(outcome.result.scope_resolution, UnmappedScope)


def test_process_message_body_returns_failed_for_invalid_message() -> None:
    outcome = process_message_body(b"{}")

    assert outcome.status == "failed"
    assert outcome.failure_kind == "invalid_message"
    assert outcome.reason == "InvalidMessage"


def test_process_message_body_returns_failed_for_invalid_normalization() -> None:
    body = (
        b'{"subject":"AzureDevOps/Auditing","eventType":"AzureDevOpsAuditEvent",'
        b'"data":{"ActionId":"Git.RepositoryCreated","ProjectId":"proj-1"}}'
    )

    outcome = process_message_body(body)

    assert outcome.status == "failed"
    assert outcome.failure_kind == "invalid_normalization"
    assert outcome.reason == "InvalidNormalization"


@patch("worker.handler.handle_queue_message", side_effect=ConfigError("invalid configuration"))
def test_process_message_body_returns_failed_for_configuration_error(_handle) -> None:
    outcome = process_message_body(b"{}")

    assert outcome.status == "failed"
    assert outcome.failure_kind == "configuration"
    assert outcome.reason == "ConfigurationError"


@patch("worker.handler.handle_queue_message", side_effect=SnykApiError("Snyk unavailable"))
def test_process_message_body_returns_failed_for_snyk_error(_handle) -> None:
    outcome = process_message_body(b"{}")

    assert outcome.status == "failed"
    assert outcome.failure_kind == "dependency"
    assert outcome.reason == "SnykApiError"


@patch(
    "worker.handler.handle_queue_message",
    return_value=HandleResult(
        settlement="dead_letter",
        dead_letter_reason="ImportJobFailed",
        dead_letter_description="retries exhausted",
    ),
)
def test_process_message_body_preserves_dead_letter_reason(_handle) -> None:
    outcome = process_message_body(b"{}")

    assert outcome.status == "failed"
    assert outcome.failure_kind == "processing"
    assert outcome.reason == "ImportJobFailed"
    assert outcome.description == "retries exhausted"


def _updated_body() -> bytes:
    fixture = Path(__file__).resolve().parents[2] / "data" / "fixtures" / "github_parsed_updated.json"
    return fixture.read_bytes()


def _property_mapping(
    *,
    default: str | None,
    include_property: bool,
    collection_path: str = "newPropertyValues",
) -> ScopeMappingSettings:
    from config.scope_mapping import parse_scope_mapping

    github_rows: list[dict[str, str]] = [
        {"orgName": "sample-org", "snykOrgId": "org-by-name"},
    ]
    if include_property:
        github_rows.append(
            {"propertyValue": "sample-project", "snykOrgId": "org-by-property"},
        )
    raw: dict[str, object] = {
        "propertyExtractors": {
            "github": {
                "collectionPath": collection_path,
                "matchField": "property_name",
                "matchValue": "azure-devops-project",
                "valueField": "value",
            },
        },
        "github-cloud-app": github_rows,
    }
    if default is not None:
        raw["defaultSnykOrgId"] = default
    return parse_scope_mapping(raw)


def _deps_for(mapping: ScopeMappingSettings) -> WorkerSyncDependencies:
    deps = _sync_deps()
    return WorkerSyncDependencies(
        sync_state=deps.sync_state,
        snyk=deps.snyk,
        ado=deps.ado,
        integration_resolver=deps.integration_resolver,
        scope_mapping=mapping,
        snyk_settings=deps.snyk_settings,
    )


def test_updated_event_imports_using_property_value(caplog) -> None:
    mapping = _property_mapping(default=None, include_property=True)
    deps = _deps_for(mapping)

    with caplog.at_level("INFO"):
        result = handle_queue_message(
            _updated_body(),
            scope_mapping=mapping,
            sync_deps=deps,
        )

    assert result.settlement == "complete"
    assert result.normalized is not None
    assert result.normalized.event_type == "repo.created"
    assert result.normalized.scope_id == "sample-org"
    assert isinstance(result.scope_resolution, ResolvedScopeMapping)
    assert result.scope_resolution.snyk_org_id == "org-by-property"
    assert "Resolved scope mapping" in caplog.text
    assert "scope_mapping_default" not in caplog.text
    deps.snyk.start_import.assert_called_once()
    assert deps.snyk.start_import.call_args.args[0] == "org-by-property"
    target = deps.snyk.start_import.call_args.args[2]
    assert target.owner == "sample-org"
    assert target.name == "sample-repo"
    deps.snyk.deactivate_all_projects_for_target.assert_not_called()
    deps.snyk.delete_snyk_target.assert_not_called()
    followup = result.scheduled_followups[0].body
    assert followup["adoProjectName"] == "sample-org"
    assert followup["extractedPropertyValue"] == "sample-project"
    assert "adoTarget" not in followup


def test_updated_event_data_path_uses_org_login() -> None:
    mapping = _property_mapping(
        default=None,
        include_property=True,
        collection_path="data.newPropertyValues",
    )
    deps = _deps_for(mapping)

    result = handle_queue_message(
        _updated_body(),
        scope_mapping=mapping,
        sync_deps=deps,
    )

    assert result.settlement == "complete"
    assert result.normalized is not None
    assert result.normalized.scope_id == "sample-org"
    assert isinstance(result.scope_resolution, ResolvedScopeMapping)
    assert result.scope_resolution.snyk_org_id == "org-by-name"
    deps.snyk.start_import.assert_called_once()
    assert deps.snyk.start_import.call_args.args[0] == "org-by-name"
    followup = result.scheduled_followups[0].body
    assert "extractedPropertyValue" not in followup


def test_updated_event_without_property_row_uses_default_org(caplog) -> None:
    mapping = _property_mapping(default="default-org", include_property=False)
    deps = _deps_for(mapping)

    with caplog.at_level("INFO"):
        result = handle_queue_message(
            _updated_body(),
            scope_mapping=mapping,
            sync_deps=deps,
        )

    assert isinstance(result.scope_resolution, ResolvedScopeMapping)
    assert result.scope_resolution.resolution == "default"
    assert result.scope_resolution.snyk_org_id == "default-org"
    assert "scope_mapping_default" in caplog.text
    assert "extracted_value=sample-project" in caplog.text
    deps.snyk.start_import.assert_called_once()
    assert deps.snyk.start_import.call_args.args[0] == "default-org"


def test_updated_event_without_mapping_or_default_skips_snyk(caplog) -> None:
    mapping = _property_mapping(default=None, include_property=False)
    deps = _deps_for(mapping)

    with caplog.at_level("WARNING"):
        result = handle_queue_message(
            _updated_body(),
            scope_mapping=mapping,
            sync_deps=deps,
        )

    assert isinstance(result.scope_resolution, UnmappedScope)
    assert result.scope_resolution.lookup_key == "sample-project"
    assert "scope_mapping_unmapped" in caplog.text
    assert "extracted_value=sample-project" in caplog.text
    assert result.scheduled_followups == ()
    deps.snyk.start_import.assert_not_called()
    deps.snyk.deactivate_all_projects_for_target.assert_not_called()
    deps.snyk.delete_snyk_target.assert_not_called()
