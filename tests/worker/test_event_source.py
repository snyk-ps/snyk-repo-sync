"""Tests for the unimplemented GitHub event-connector source."""

import pytest

from config.errors import ConfigError
from worker.event_source import open_github_event_source


def test_open_github_event_source_reports_pending_contract() -> None:
    with pytest.raises(ConfigError, match="REST API contract is pending"):
        open_github_event_source()
