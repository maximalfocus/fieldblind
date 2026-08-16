"""Shared fixtures: one real loopback server, fresh fixture state, and captured service logs."""

from __future__ import annotations

import json
import logging
import threading
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import httpx
import pytest
import uvicorn

from fieldblind.config import Settings
from fieldblind.observability import LOGGER_NAME
from fieldblind.persistence import create_database_engine, reset_state
from fieldblind.secure_app import create_secure_app
from fieldblind.service import set_pre_commit_hook

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path

    from sqlalchemy.engine import Engine

SERVER_START_TIMEOUT_SECONDS = 15.0
SERVER_POLL_SECONDS = 0.01


class RecordingHandler(logging.Handler):
    """Collect every bounded JSON line the service emits."""

    def __init__(self) -> None:
        super().__init__()
        self.lines: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.lines.append(record.getMessage())

    def reset(self) -> None:
        """Drop every captured line."""
        self.lines.clear()

    def events(self, name: str) -> list[dict[str, Any]]:
        """Return every captured event with this event name."""
        found: list[dict[str, Any]] = []
        for line in list(self.lines):
            payload = json.loads(line)
            if payload.get("event") == name:
                found.append(payload)
        return found

    def payload_text(self) -> str:
        """Return every captured event as text, minus the random correlation identifiers.

        Correlation identifiers are random hex, so leaving them in would make substring redaction
        checks match by accident.
        """
        rendered: list[str] = []
        for line in list(self.lines):
            payload = json.loads(line)
            payload.pop("request_id", None)
            rendered.append(json.dumps(payload, sort_keys=True))
        return "\n".join(rendered)


@dataclass(frozen=True, slots=True)
class LoopbackService:
    """A running secure service plus the handles a test needs to inspect it."""

    client: httpx.Client
    engine: Engine
    logs: RecordingHandler


@pytest.fixture(scope="session")
def _database_path(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return tmp_path_factory.mktemp("fieldblind") / "secure.db"


@pytest.fixture(scope="session")
def service(_database_path: Path) -> Iterator[LoopbackService]:
    """Serve the secure app over real loopback HTTP for the whole session."""
    settings = Settings(database_path=_database_path)
    app = create_secure_app(settings)
    config = uvicorn.Config(app, host="127.0.0.1", port=0, log_level="warning")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()

    deadline = time.monotonic() + SERVER_START_TIMEOUT_SECONDS
    while not server.started:
        if time.monotonic() > deadline:
            server.should_exit = True
            pytest.fail("the loopback service did not become ready")
        time.sleep(SERVER_POLL_SECONDS)

    port = server.servers[0].sockets[0].getsockname()[1]
    handler = RecordingHandler()
    logging.getLogger(LOGGER_NAME).addHandler(handler)

    engine = create_database_engine(_database_path)
    with httpx.Client(base_url=f"http://127.0.0.1:{port}", timeout=10.0) as client:
        yield LoopbackService(client=client, engine=engine, logs=handler)

    logging.getLogger(LOGGER_NAME).removeHandler(handler)
    server.should_exit = True
    thread.join(timeout=SERVER_START_TIMEOUT_SECONDS)


@pytest.fixture(autouse=True)
def _fresh_state(service: LoopbackService) -> Iterator[None]:
    """Start every case from the same disposable fixture and no captured logs."""
    set_pre_commit_hook(None)
    reset_state(service.engine)
    service.logs.reset()
    yield
    set_pre_commit_hook(None)
