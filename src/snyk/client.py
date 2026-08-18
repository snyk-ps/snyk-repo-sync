"""HTTP client for Snyk REST APIs used by lifecycle sync."""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any, Callable, Literal, Protocol

from snyk.target_lookup import (
    extract_next_link,
    normalize_repo_name,
    parse_project_ids,
    parse_target_records,
    select_target_id,
)

ImportJobState = Literal["pending", "complete", "failed"]
REST_API_VERSION = "2024-10-15"
DEFAULT_SOURCE_TYPE = "azure-repos"


class HttpResponse(Protocol):
    """Minimal HTTP response protocol for testing."""

    def read(self) -> bytes: ...

    @property
    def status(self) -> int: ...


HttpOpener = Callable[..., HttpResponse]


class SnykApiError(Exception):
    """Raised when a Snyk API request fails."""

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        transient: bool = False,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.transient = transient


@dataclass(frozen=True)
class SnykIntegration:
    """Snyk org integration reference."""

    id: str
    integration_type: str


@dataclass(frozen=True)
class ImportTarget:
    """Repository target passed to the Snyk import API."""

    owner: str
    name: str
    branch: str


@dataclass(frozen=True)
class ImportJobStatus:
    """Normalized import job status from Snyk."""

    job_id: str
    state: ImportJobState
    target_id: str | None = None
    failure_reason: str | None = None


class SnykClient:
    """Thin wrapper around Snyk REST endpoints used by the worker."""

    def __init__(
        self,
        token: str,
        *,
        base_url: str = "https://api.snyk.io",
        opener: HttpOpener | None = None,
        max_rate_limit_retries: int = 3,
    ) -> None:
        self._token = token
        self._base_url = base_url.rstrip("/")
        self._opener = opener or urllib.request.urlopen
        self._max_rate_limit_retries = max_rate_limit_retries

    def list_integrations(self, org_id: str) -> list[SnykIntegration]:
        """List integrations configured for a Snyk organization."""
        payload = self._request_json("GET", f"/v1/org/{org_id}/integrations")
        if not isinstance(payload, dict):
            raise SnykApiError("integrations response must be a JSON object")
        return _parse_integrations_payload(payload)

    def start_import(
        self,
        org_id: str,
        integration_id: str,
        target: ImportTarget,
    ) -> str:
        """Trigger a repository import and return the import job id."""
        branch = target.branch.strip()
        if not branch:
            raise SnykApiError("import target branch is required")
        body = {
            "target": {
                "owner": target.owner,
                "name": target.name,
                "branch": branch,
            },
        }
        path = f"/v1/org/{org_id}/integrations/{integration_id}/import"
        payload, response_headers = self._request_with_headers(
            "POST",
            path,
            body=body,
        )
        location = _response_header(response_headers, "Location")
        job_id = _extract_job_id_from_location(location) if location else None
        if job_id is None:
            job_id = _extract_job_id(payload)
        if job_id is None:
            raise SnykApiError("import response missing job id")
        return job_id

    def get_import_job(
        self,
        org_id: str,
        integration_id: str,
        job_id: str,
    ) -> ImportJobStatus:
        """Fetch normalized import job status."""
        payload = self._request_json(
            "GET",
            f"/v1/org/{org_id}/integrations/{integration_id}/import/{job_id}",
        )
        return _normalize_import_job(job_id, payload)

    def find_target_id(
        self,
        org_id: str,
        *,
        owner: str,
        repo_name: str,
        branch: str = "",
        source_type: str = DEFAULT_SOURCE_TYPE,
    ) -> str | None:
        """Find a Snyk target id for an imported ADO repository."""
        query = {
            "version": REST_API_VERSION,
            "source_types": source_type,
            "display_name": normalize_repo_name(repo_name),
            "limit": "100",
            "exclude_empty": "false",
        }
        path = f"/rest/orgs/{org_id}/targets"
        records: list[dict[str, Any]] = []
        next_link: str | None = None
        while True:
            if next_link:
                payload = self._request_rest_url("GET", next_link)
            else:
                payload = self._request_rest("GET", path, query=query)
            records.extend(parse_target_records(payload))
            next_link = extract_next_link(payload)
            if not next_link:
                break
        return select_target_id(
            records,
            owner=owner,
            repo_name=repo_name,
            branch=branch,
        )

    def list_project_ids_for_target(self, org_id: str, target_id: str) -> list[str]:
        """Return Snyk project ids associated with a target."""
        path = f"/rest/orgs/{org_id}/projects"
        query = {
            "version": REST_API_VERSION,
            "target_id": target_id,
            "limit": "100",
        }
        project_ids: list[str] = []
        next_link: str | None = None
        while True:
            if next_link:
                payload = self._request_rest_url("GET", next_link)
            else:
                payload = self._request_rest("GET", path, query=query)
            project_ids.extend(parse_project_ids(payload))
            next_link = extract_next_link(payload)
            if not next_link:
                break
        return project_ids

    def deactivate_project(self, org_id: str, project_id: str) -> None:
        """Deactivate a single Snyk project."""
        self._request_json(
            "POST",
            f"/v1/org/{org_id}/project/{project_id}/deactivate",
        )

    def deactivate_all_projects_for_target(self, org_id: str, target_id: str) -> int:
        """Deactivate every project under a Snyk target and return the count."""
        project_ids = self.list_project_ids_for_target(org_id, target_id)
        for project_id in project_ids:
            self.deactivate_project(org_id, project_id)
        return len(project_ids)

    def delete_snyk_target(self, org_id: str, target_id: str) -> None:
        """Delete a Snyk target and all associated projects."""
        self._request_rest(
            "DELETE",
            f"/rest/orgs/{org_id}/targets/{target_id}",
            query={"version": REST_API_VERSION},
        )

    def _request_json(
        self,
        method: str,
        path: str,
        *,
        body: dict[str, Any] | None = None,
    ) -> Any:
        attempt = 0
        while True:
            try:
                payload, _headers = self._request_with_headers(method, path, body=body)
                return payload
            except SnykApiError as exc:
                if exc.transient and attempt < self._max_rate_limit_retries:
                    attempt += 1
                    time.sleep(min(2**attempt, 30))
                    continue
                raise

    def _request_with_headers(
        self,
        method: str,
        path: str,
        *,
        body: dict[str, Any] | None = None,
    ) -> tuple[Any, Any]:
        attempt = 0
        while True:
            try:
                return self._request_with_headers_once(method, path, body=body)
            except SnykApiError as exc:
                if exc.transient and attempt < self._max_rate_limit_retries:
                    attempt += 1
                    time.sleep(min(2**attempt, 30))
                    continue
                raise

    def _request_with_headers_once(
        self,
        method: str,
        path: str,
        *,
        body: dict[str, Any] | None = None,
    ) -> tuple[Any, Any]:
        url = f"{self._base_url}{path}"
        data = None
        headers = {
            "Authorization": f"token {self._token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        if body is not None:
            data = json.dumps(body).encode("utf-8")
        request = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with self._opener(request, timeout=30) as response:
                raw = response.read()
                response_headers = getattr(response, "headers", None)
                if response.status == 204 or not raw:
                    return {}, response_headers
                return json.loads(raw.decode("utf-8")), response_headers
        except urllib.error.HTTPError as exc:
            message = exc.read().decode("utf-8", errors="replace")
            transient = exc.code == 429 or exc.code >= 500
            if exc.code in {404, 400}:
                transient = False
            raise SnykApiError(
                f"Snyk API {method} {path} failed with {exc.code}: {message}",
                status_code=exc.code,
                transient=transient,
            ) from exc
        except urllib.error.URLError as exc:
            raise SnykApiError(
                f"Snyk API {method} {path} failed: {exc.reason}",
                transient=True,
            ) from exc
        except json.JSONDecodeError as exc:
            raise SnykApiError(
                f"Snyk API {method} {path} returned invalid JSON",
            ) from exc

    def _request_json_once(
        self,
        method: str,
        path: str,
        *,
        body: dict[str, Any] | None = None,
    ) -> Any:
        payload, _headers = self._request_with_headers_once(method, path, body=body)
        return payload

    def _request_rest(
        self,
        method: str,
        path: str,
        *,
        query: dict[str, str] | None = None,
        body: dict[str, Any] | None = None,
    ) -> Any:
        attempt = 0
        while True:
            try:
                return self._request_rest_once(method, path, query=query, body=body)
            except SnykApiError as exc:
                if exc.transient and attempt < self._max_rate_limit_retries:
                    attempt += 1
                    time.sleep(min(2**attempt, 30))
                    continue
                raise

    def _request_rest_once(
        self,
        method: str,
        path: str,
        *,
        query: dict[str, str] | None = None,
        body: dict[str, Any] | None = None,
    ) -> Any:
        url = f"{self._base_url}{path}"
        if query:
            url = f"{url}?{urllib.parse.urlencode(query, doseq=True)}"
        return self._request_rest_url(method, url, body=body)

    def _request_rest_url(
        self,
        method: str,
        url: str,
        *,
        body: dict[str, Any] | None = None,
    ) -> Any:
        attempt = 0
        while True:
            try:
                return self._request_rest_url_once(method, url, body=body)
            except SnykApiError as exc:
                if exc.transient and attempt < self._max_rate_limit_retries:
                    attempt += 1
                    time.sleep(min(2**attempt, 30))
                    continue
                raise

    def _request_rest_url_once(
        self,
        method: str,
        url: str,
        *,
        body: dict[str, Any] | None = None,
    ) -> Any:
        data = None
        headers = {
            "Authorization": f"token {self._token}",
            "Accept": "application/vnd.api+json",
            "Content-Type": "application/vnd.api+json",
        }
        if body is not None:
            data = json.dumps(body).encode("utf-8")
        request = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with self._opener(request, timeout=30) as response:
                raw = response.read()
                if response.status == 204 or not raw:
                    return {}
                return json.loads(raw.decode("utf-8"))
        except urllib.error.HTTPError as exc:
            message = exc.read().decode("utf-8", errors="replace")
            transient = exc.code == 429 or exc.code >= 500
            if exc.code in {404, 400}:
                transient = False
            raise SnykApiError(
                f"Snyk API {method} {url} failed with {exc.code}: {message}",
                status_code=exc.code,
                transient=transient,
            ) from exc
        except urllib.error.URLError as exc:
            raise SnykApiError(
                f"Snyk API {method} {url} failed: {exc.reason}",
                transient=True,
            ) from exc
        except json.JSONDecodeError as exc:
            raise SnykApiError(
                f"Snyk API {method} {url} returned invalid JSON",
            ) from exc


def _parse_integrations_payload(payload: dict[str, Any]) -> list[SnykIntegration]:
    """Parse GET /v1/org/{orgId}/integrations response into integration records."""
    integrations: list[SnykIntegration] = []
    for key, value in payload.items():
        if not isinstance(key, str) or not key.strip():
            continue
        if isinstance(value, str) and value.strip():
            integrations.append(
                SnykIntegration(
                    id=value.strip(),
                    integration_type=key.strip(),
                ),
            )
            continue
        if isinstance(value, dict):
            integration_type = value.get("type")
            if isinstance(integration_type, str) and integration_type.strip():
                integrations.append(
                    SnykIntegration(
                        id=key.strip(),
                        integration_type=integration_type.strip(),
                    ),
                )
    return integrations


def _response_header(headers: Any, name: str) -> str | None:
    """Return a response header value when headers are available."""
    if headers is None or not hasattr(headers, "get"):
        return None
    value = headers.get(name)
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _extract_job_id_from_location(location: str) -> str | None:
    """Extract import job id from the Snyk import API Location header URL."""
    parts = location.rstrip("/").split("/")
    try:
        import_index = parts.index("import")
    except ValueError:
        return None
    if import_index + 1 >= len(parts):
        return None
    job_id = parts[import_index + 1].strip()
    return job_id or None


def _extract_job_id(payload: Any) -> str | None:
    if isinstance(payload, dict):
        for key in ("id", "jobId", "job_id"):
            value = payload.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    return None


def _normalize_import_job(job_id: str, payload: Any) -> ImportJobStatus:
    if not isinstance(payload, dict):
        raise SnykApiError("import job response must be a JSON object")

    status_raw = payload.get("status") or payload.get("state")
    status_text = status_raw.lower() if isinstance(status_raw, str) else "pending"
    if status_text in {"succeeded", "success", "complete", "completed", "done"}:
        state: ImportJobState = "complete"
    elif status_text in {"failed", "failure", "error"}:
        state = "failed"
    else:
        state = "pending"

    target_id = payload.get("projectId") or payload.get("targetId")
    if isinstance(target_id, str) and not target_id.strip():
        target_id = None

    failure_reason = payload.get("failureReason") or payload.get("error")
    if isinstance(failure_reason, str) and not failure_reason.strip():
        failure_reason = None

    return ImportJobStatus(
        job_id=job_id,
        state=state,
        target_id=target_id.strip() if isinstance(target_id, str) else None,
        failure_reason=failure_reason.strip() if isinstance(failure_reason, str) else None,
    )
