"""Tests for Snyk REST client."""

import io
import json
from email.message import Message
from urllib.parse import parse_qs, urlparse

import urllib.error

import pytest

from snyk.client import ImportTarget, SnykApiError, SnykClient


class FakeHTTPResponse:
    """Minimal HTTP response for urllib tests."""

    def __init__(
        self,
        status: int,
        payload: object,
        *,
        headers: dict[str, str] | None = None,
    ) -> None:
        self.status = status
        self._payload = payload
        message = Message()
        for key, value in (headers or {}).items():
            message[key] = value
        self.headers = message

    def read(self) -> bytes:
        if self._payload == b"":
            return b""
        if isinstance(self._payload, (bytes, bytearray)):
            return bytes(self._payload)
        return json.dumps(self._payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None


def test_list_integrations_parses_v1_response() -> None:
    def opener(request, timeout=30):
        assert request.get_method() == "GET"
        return FakeHTTPResponse(
            200,
            {
                "azure-repos": "7474fa46-88bd-4fa4-8442-971c246ed662",
                "github": "81b3ce18-6b93-4978-88df-8f51a5170897",
                "github-enterprise": "4509bd6c-2aa4-4c87-a72c-8311cfd39abb",
            },
        )

    client = SnykClient("token", opener=opener)
    integrations = client.list_integrations("org-1")

    assert len(integrations) == 3
    by_type = {item.integration_type: item.id for item in integrations}
    assert by_type["azure-repos"] == "7474fa46-88bd-4fa4-8442-971c246ed662"
    assert by_type["github"] == "81b3ce18-6b93-4978-88df-8f51a5170897"


def test_list_integrations_parses_legacy_object_response() -> None:
    def opener(request, timeout=30):
        return FakeHTTPResponse(
            200,
            {"integration-1": {"type": "azure-repos", "name": "ADO"}},
        )

    client = SnykClient("token", opener=opener)
    integrations = client.list_integrations("org-1")

    assert len(integrations) == 1
    assert integrations[0].id == "integration-1"
    assert integrations[0].integration_type == "azure-repos"


def test_start_import_returns_job_id_from_location_header() -> None:
    def opener(request, timeout=30):
        assert request.get_method() == "POST"
        return FakeHTTPResponse(
            201,
            b"",
            headers={
                "Location": (
                    "https://api.snyk.io/v1/org/org-1/integrations/integration-1/"
                    "import/job-123"
                ),
            },
        )

    client = SnykClient("token", opener=opener)
    job_id = client.start_import(
        "org-1",
        "integration-1",
        ImportTarget(owner="proj", name="repo", branch="main"),
    )

    assert job_id == "job-123"


def test_start_import_always_includes_branch_in_payload() -> None:
    captured: dict[str, object] = {}

    def opener(request, timeout=30):
        captured["body"] = json.loads(request.data.decode("utf-8"))
        return FakeHTTPResponse(
            201,
            b"",
            headers={
                "Location": (
                    "https://api.snyk.io/v1/org/org-1/integrations/integration-1/"
                    "import/job-456"
                ),
            },
        )

    client = SnykClient("token", opener=opener)
    job_id = client.start_import(
        "org-1",
        "integration-1",
        ImportTarget(owner="proj", name="repo", branch="master"),
    )

    assert job_id == "job-456"
    target = captured["body"]["target"]  # type: ignore[index]
    assert target == {"owner": "proj", "name": "repo", "branch": "master"}


def test_start_import_rejects_empty_branch() -> None:
    client = SnykClient("token", opener=lambda *_args, **_kwargs: None)

    with pytest.raises(SnykApiError, match="branch is required"):
        client.start_import(
            "org-1",
            "integration-1",
            ImportTarget(owner="proj", name="repo", branch="  "),
        )


def test_start_import_falls_back_to_body_job_id() -> None:
    def opener(request, timeout=30):
        return FakeHTTPResponse(200, {"id": "job-456"})

    client = SnykClient("token", opener=opener)
    job_id = client.start_import(
        "org-1",
        "integration-1",
        ImportTarget(owner="proj", name="repo", branch="main"),
    )

    assert job_id == "job-456"


def test_start_import_raises_when_job_id_missing() -> None:
    def opener(request, timeout=30):
        return FakeHTTPResponse(201, b"")

    client = SnykClient("token", opener=opener)

    with pytest.raises(SnykApiError, match="import response missing job id"):
        client.start_import(
            "org-1",
            "integration-1",
            ImportTarget(owner="proj", name="repo", branch="main"),
        )


def test_get_import_job_normalizes_complete() -> None:
    def opener(request, timeout=30):
        return FakeHTTPResponse(200, {"status": "completed", "projectId": "target-1"})

    client = SnykClient("token", opener=opener)
    status = client.get_import_job("org-1", "integration-1", "job-123")

    assert status.state == "complete"
    assert status.target_id == "target-1"


def test_deactivate_all_projects_and_delete_target() -> None:
    requests: list[tuple[str, str]] = []

    def opener(request, timeout=30):
        requests.append((request.get_method(), request.full_url))
        return FakeHTTPResponse(204, b"")

    client = SnykClient("token", opener=opener)
    client.deactivate_project("org-1", "project-1")
    client.delete_snyk_target("org-1", "target-1")

    assert requests[0][0] == "POST"
    assert requests[0][1].endswith("/v1/org/org-1/project/project-1/deactivate")
    assert requests[1][0] == "DELETE"
    assert "/rest/orgs/org-1/targets/target-1" in requests[1][1]


def test_find_target_id_includes_exclude_empty_false() -> None:
    def opener(request, timeout=30):
        assert request.get_method() == "GET"
        assert "/rest/orgs/org-1/targets" in request.full_url
        query = parse_qs(urlparse(request.full_url).query)
        assert query.get("exclude_empty") == ["false"]
        return FakeHTTPResponse(200, {"data": []})

    client = SnykClient("token", opener=opener)
    assert (
        client.find_target_id(
            "org-1",
            owner="proj",
            repo_name="demo",
            branch="main",
        )
        is None
    )


def test_find_target_id_matches_display_name() -> None:
    def opener(request, timeout=30):
        assert request.get_method() == "GET"
        assert "/rest/orgs/org-1/targets" in request.full_url
        return FakeHTTPResponse(
            200,
            {
                "data": [
                    {
                        "id": "target-1",
                        "attributes": {"display_name": "proj/demo(main)"},
                    }
                ],
            },
        )

    client = SnykClient("token", opener=opener)
    target_id = client.find_target_id(
        "org-1",
        owner="proj",
        repo_name="demo",
        branch="main",
    )

    assert target_id == "target-1"


def test_find_target_id_matches_empty_target() -> None:
    """Empty targets (zero projects) must be returned when exclude_empty=false."""

    def opener(request, timeout=30):
        assert request.get_method() == "GET"
        query = parse_qs(urlparse(request.full_url).query)
        assert query.get("exclude_empty") == ["false"]
        return FakeHTTPResponse(
            200,
            {
                "data": [
                    {
                        "id": "target-empty",
                        "attributes": {
                            "display_name": "snykDemoProject/ignored-regex-archived(main)",
                        },
                    }
                ],
            },
        )

    client = SnykClient("token", opener=opener)
    target_id = client.find_target_id(
        "org-1",
        owner="snykDemoProject",
        repo_name="ignored-regex-archived",
        branch="main",
    )

    assert target_id == "target-empty"


def test_list_project_ids_for_target() -> None:
    def opener(request, timeout=30):
        assert request.get_method() == "GET"
        assert "/rest/orgs/org-1/projects" in request.full_url
        return FakeHTTPResponse(
            200,
            {
                "data": [
                    {"id": "project-1"},
                    {"id": "project-2"},
                ],
            },
        )

    client = SnykClient("token", opener=opener)
    project_ids = client.list_project_ids_for_target("org-1", "target-1")

    assert project_ids == ["project-1", "project-2"]


def test_deactivate_all_projects_for_target() -> None:
    calls: list[str] = []

    def opener(request, timeout=30):
        calls.append(request.full_url)
        if "/rest/orgs/org-1/projects" in request.full_url:
            return FakeHTTPResponse(
                200,
                {"data": [{"id": "project-1"}, {"id": "project-2"}]},
            )
        return FakeHTTPResponse(204, b"")

    client = SnykClient("token", opener=opener)
    count = client.deactivate_all_projects_for_target("org-1", "target-1")

    assert count == 2
    assert any("/project/project-1/deactivate" in call for call in calls)
    assert any("/project/project-2/deactivate" in call for call in calls)


def test_rate_limit_retries_then_raises() -> None:
    attempts = {"count": 0}

    def opener(request, timeout=30):
        attempts["count"] += 1
        if attempts["count"] < 3:
            error = io.BytesIO(b"rate limited")
            raise urllib.error.HTTPError(
                request.full_url,
                429,
                "Too Many Requests",
                hdrs=None,
                fp=error,
            )
        return FakeHTTPResponse(
            201,
            b"",
            headers={
                "Location": (
                    "https://api.snyk.io/v1/org/org-1/integrations/integration-1/import/job-1"
                ),
            },
        )

    client = SnykClient("token", opener=opener, max_rate_limit_retries=3)
    job_id = client.start_import(
        "org-1",
        "integration-1",
        ImportTarget(owner="proj", name="repo", branch="main"),
    )

    assert job_id == "job-1"
    assert attempts["count"] == 3
