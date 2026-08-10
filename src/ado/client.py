"""HTTP client for Azure DevOps Git REST APIs."""

from __future__ import annotations

import base64
import json
import urllib.error
import urllib.request
from typing import Any, Callable, Protocol

from worker.normalize import strip_branch_ref


class HttpResponse(Protocol):
    """Minimal HTTP response protocol for testing."""

    def read(self) -> bytes: ...

    @property
    def status(self) -> int: ...


HttpOpener = Callable[..., HttpResponse]


class AdoApiError(Exception):
    """Raised when an Azure DevOps API request fails."""

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class AdoClient:
    """Thin wrapper around ADO Git repository endpoints used by lifecycle sync."""

    def __init__(
        self,
        pat: str,
        *,
        organization: str,
        host: str = "dev.azure.com",
        opener: HttpOpener | None = None,
    ) -> None:
        self._pat = pat
        self._organization = organization.strip()
        self._host = host.strip().rstrip("/")
        self._opener = opener or urllib.request.urlopen

    def get_repository_default_branch(self, repository_id: str) -> str:
        """Return the repository default branch name without ``refs/heads/`` prefix."""
        repo_id = repository_id.strip()
        if not repo_id:
            raise AdoApiError("repository id is required to resolve default branch")

        path = (
            f"/{self._organization}/_apis/git/repositories/{repo_id}"
            "?api-version=7.1"
        )
        payload = self._request_json("GET", path)
        if not isinstance(payload, dict):
            raise AdoApiError("repository response must be a JSON object")

        default_branch = payload.get("defaultBranch")
        if not isinstance(default_branch, str) or not default_branch.strip():
            raise AdoApiError(
                f"repository {repo_id} response missing defaultBranch",
            )

        branch = strip_branch_ref(default_branch.strip())
        if not branch:
            raise AdoApiError(
                f"repository {repo_id} defaultBranch is empty after normalization",
            )
        return branch

    def _request_json(self, method: str, path: str) -> Any:
        url = f"https://{self._host}{path}"
        credentials = base64.b64encode(f":{self._pat}".encode("utf-8")).decode("ascii")
        headers = {
            "Authorization": f"Basic {credentials}",
            "Accept": "application/json",
        }
        request = urllib.request.Request(url, headers=headers, method=method)
        try:
            with self._opener(request, timeout=30) as response:
                raw = response.read()
                if response.status == 204 or not raw:
                    return {}
                return json.loads(raw.decode("utf-8"))
        except urllib.error.HTTPError as exc:
            message = exc.read().decode("utf-8", errors="replace")
            raise AdoApiError(
                f"ADO API {method} {path} failed with {exc.code}: {message}",
                status_code=exc.code,
            ) from exc
        except urllib.error.URLError as exc:
            raise AdoApiError(
                f"ADO API {method} {path} failed: {exc.reason}",
            ) from exc
        except json.JSONDecodeError as exc:
            raise AdoApiError(
                f"ADO API {method} {path} returned invalid JSON",
            ) from exc
