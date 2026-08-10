"""Tests for ADO REST client."""

import json
from email.message import Message

import pytest
import urllib.error

from ado.client import AdoApiError, AdoClient


class FakeHTTPResponse:
    """Minimal HTTP response for urllib tests."""

    def __init__(self, status: int, payload: object) -> None:
        self.status = status
        self._payload = payload

    def read(self) -> bytes:
        if isinstance(self._payload, (bytes, bytearray)):
            return bytes(self._payload)
        return json.dumps(self._payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None


def test_get_repository_default_branch_strips_ref_prefix() -> None:
    captured: dict[str, str] = {}

    def opener(request, timeout=30):
        captured["url"] = request.full_url
        captured["authorization"] = request.get_header("Authorization")
        return FakeHTTPResponse(
            200,
            {"defaultBranch": "refs/heads/master"},
        )

    client = AdoClient("pat-token", organization="contoso", opener=opener)
    branch = client.get_repository_default_branch("repo-id")

    assert branch == "master"
    assert captured["url"].endswith("/contoso/_apis/git/repositories/repo-id?api-version=7.1")
    assert captured["authorization"].startswith("Basic ")


def test_get_repository_default_branch_rejects_empty_repository_id() -> None:
    client = AdoClient("pat-token", organization="contoso", opener=lambda *_args, **_kwargs: None)

    with pytest.raises(AdoApiError, match="repository id is required"):
        client.get_repository_default_branch("  ")


def test_get_repository_default_branch_raises_when_missing_from_response() -> None:
    def opener(request, timeout=30):
        return FakeHTTPResponse(200, {"name": "demo"})

    client = AdoClient("pat-token", organization="contoso", opener=opener)

    with pytest.raises(AdoApiError, match="missing defaultBranch"):
        client.get_repository_default_branch("repo-id")


def test_get_repository_default_branch_raises_on_http_error() -> None:
    def opener(request, timeout=30):
        error = urllib.error.HTTPError(
            request.full_url,
            404,
            "Not Found",
            hdrs=Message(),
            fp=None,
        )
        error.read = lambda: b"repo not found"  # type: ignore[method-assign]
        raise error

    client = AdoClient("pat-token", organization="contoso", opener=opener)

    with pytest.raises(AdoApiError, match="failed with 404"):
        client.get_repository_default_branch("repo-id")
