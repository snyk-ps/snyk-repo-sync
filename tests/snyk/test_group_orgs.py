"""Tests for Snyk group org listing, cache, and name comparison."""

import json
from email.message import Message

from snyk.client import GROUP_ORG_CACHE_TTL_SECONDS, SnykClient, SnykGroupOrg
from snyk.group_orgs import match_group_orgs


class _Response:
    def __init__(self, payload: object) -> None:
        self.status = 200
        self.headers = Message()
        self._payload = payload

    def read(self) -> bytes:
        return json.dumps(self._payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None


def test_exact_org_name_match() -> None:
    orgs = [SnykGroupOrg(id="1", name="Platform"), SnykGroupOrg(id="2", name="platform")]

    matches = match_group_orgs(" Platform ", orgs, normalize=False)

    assert [org.id for org in matches] == ["1"]


def test_normalized_org_name_matches_systemes_centraux() -> None:
    orgs = [SnykGroupOrg(id="org-1", name="systemes centraux")]

    matches = match_group_orgs("Systèmes Centraux", orgs, normalize=True)

    assert [org.id for org in matches] == ["org-1"]


def test_normalize_leaves_punctuation_significant() -> None:
    orgs = [SnykGroupOrg(id="org-1", name="Systemes-Centraux")]

    matches = match_group_orgs("Systemes Centraux", orgs, normalize=True)

    assert matches == []


def test_list_group_orgs_skips_incomplete_entries() -> None:
    def opener(request, timeout=30):
        assert request.get_method() == "GET"
        assert request.full_url.endswith("/v1/group/group-1/orgs")
        return _Response(
            {
                "orgs": [
                    {"id": "ok", "name": "Platform"},
                    {"name": "missing-id"},
                    {"id": "missing-name"},
                    {"id": "  ", "name": "blank-id"},
                    {"id": "blank-name", "name": " "},
                    "not-an-object",
                ],
            },
        )

    client = SnykClient("super-secret-token", opener=opener)

    assert client.list_group_orgs("group-1") == [SnykGroupOrg(id="ok", name="Platform")]


def test_list_group_orgs_refreshes_after_fifteen_minutes() -> None:
    now = {"value": 1_000.0}
    calls = {"count": 0}

    def opener(request, timeout=30):
        calls["count"] += 1
        return _Response({"orgs": [{"id": f"org-{calls['count']}", "name": "Platform"}]})

    client = SnykClient("token", opener=opener, clock=lambda: now["value"])

    first = client.list_group_orgs("group-1")
    second = client.list_group_orgs("group-1")
    now["value"] += GROUP_ORG_CACHE_TTL_SECONDS
    third = client.list_group_orgs("group-1")
    now["value"] += 0.001
    fourth = client.list_group_orgs("group-1")

    assert first == second == [SnykGroupOrg(id="org-1", name="Platform")]
    assert third == [SnykGroupOrg(id="org-1", name="Platform")]
    assert fourth == [SnykGroupOrg(id="org-2", name="Platform")]
    assert calls["count"] == 2
