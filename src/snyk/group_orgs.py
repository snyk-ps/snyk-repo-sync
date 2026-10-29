"""Compare a scope candidate to Snyk group organization names."""

from __future__ import annotations

import unicodedata
from collections.abc import Sequence
from typing import Protocol


class _NamedOrg(Protocol):
    id: str
    name: str


def match_group_orgs(
    candidate: str,
    orgs: Sequence[_NamedOrg],
    *,
    normalize: bool,
) -> list[_NamedOrg]:
    """Return group orgs whose names equal the candidate.

    Both sides are trimmed. When ``normalize`` is true, comparison applies
    Unicode NFKD, removes nonspacing marks, and casefolds. Punctuation and
    internal spaces stay significant.
    """
    if normalize:
        needle = _normalize_org_name(candidate)
        return [org for org in orgs if _normalize_org_name(org.name) == needle]
    needle = candidate.strip()
    return [org for org in orgs if org.name.strip() == needle]


def _normalize_org_name(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value.strip())
    without_marks = "".join(char for char in decomposed if unicodedata.category(char) != "Mn")
    return without_marks.casefold()
