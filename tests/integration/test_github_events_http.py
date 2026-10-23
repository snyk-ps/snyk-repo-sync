"""Local integration test for Uvicorn GitHub event ingress."""

import socket
import threading
import time
import urllib.request
from pathlib import Path
from unittest.mock import patch

import pytest
import uvicorn

from config.scope_mapping import ScopeMappingSettings
from config.settings import HttpSettings
from worker.followup import ScheduledFollowUp
from worker.handler import HandleResult, ProcessingOutcome
from worker.http_ingress import GitHubEventsApp

FIXTURES = Path(__file__).resolve().parents[2] / "data" / "fixtures"

pytestmark = pytest.mark.integration


class _Scheduler:
    def __init__(self) -> None:
        self.scheduled: list[tuple[dict, int]] = []

    def schedule(self, body: dict, *, delay_seconds: int) -> None:
        self.scheduled.append((body, delay_seconds))


def test_uvicorn_acknowledges_only_after_followup_is_scheduled() -> None:
    scheduler = _Scheduler()
    followup = ScheduledFollowUp(
        body={"syncPhase": "import_poll", "retryCount": 0},
        delay_seconds=30,
    )
    app = GitHubEventsApp(
        HttpSettings(),
        scope_mapping=ScopeMappingSettings.empty(),
        sync_deps=None,
        followup_scheduler=scheduler,
    )
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen()
    port = listener.getsockname()[1]
    server = uvicorn.Server(
        uvicorn.Config(
            app,
            log_level="critical",
            access_log=False,
        )
    )
    thread = threading.Thread(
        target=server.run,
        kwargs={"sockets": [listener]},
        daemon=True,
    )
    body = (FIXTURES / "github_parsed_renamed.json").read_bytes()
    outcome = ProcessingOutcome(
        status="completed",
        result=HandleResult(scheduled_followups=(followup,)),
    )

    with patch("worker.http_ingress.process_message_body", return_value=outcome):
        thread.start()
        deadline = time.monotonic() + 5
        while not server.started and time.monotonic() < deadline:
            time.sleep(0.01)
        assert server.started
        try:
            request = urllib.request.Request(
                f"http://127.0.0.1:{port}/github-events",
                data=body,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(request, timeout=5) as response:
                assert response.status == 204
                assert scheduler.scheduled == [(followup.body, 30)]
        finally:
            server.should_exit = True
            thread.join(timeout=5)
            listener.close()

    assert not thread.is_alive()
