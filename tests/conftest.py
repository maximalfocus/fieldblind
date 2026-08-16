"""Shared fixtures: both variants served over real loopback, fresh state, and captured logs."""

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
from fieldblind.vulnerable_app import create_vulnerable_app

if TYPE_CHECKING:
    from collections.abc import Iterator

    from fastapi import FastAPI
    from sqlalchemy.engine import Engine

SERVER_START_TIMEOUT_SECONDS = 15.0
SERVER_POLL_SECONDS = 0.01


class RecordingHandler(logging.Handler):
    """Collect every bounded JSON line the services emit."""

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
    """A running service plus the handles a test needs to inspect it."""

    client: httpx.Client
    engine: Engine
    logs: RecordingHandler


@dataclass(slots=True)
class _RunningServer:
    server: uvicorn.Server
    thread: threading.Thread
    port: int


def _serve(app: FastAPI) -> _RunningServer:
    config = uvicorn.Config(app, host="127.0.0.1", port=0, log_level="warning")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()

    deadline = time.monotonic() + SERVER_START_TIMEOUT_SECONDS
    while not server.started:
        if time.monotonic() > deadline:
            server.should_exit = True
            pytest.fail("a loopback service did not become ready")
        time.sleep(SERVER_POLL_SECONDS)

    port: int = server.servers[0].sockets[0].getsockname()[1]
    return _RunningServer(server=server, thread=thread, port=port)


@dataclass(frozen=True, slots=True)
class _Stack:
    secure: LoopbackService
    vulnerable: LoopbackService


@pytest.fixture(scope="session")
def _stack(tmp_path_factory: pytest.TempPathFactory) -> Iterator[_Stack]:
    """Serve both variants for the whole session, each over its own disposable database."""
    root = tmp_path_factory.mktemp("fieldblind")
    secure_path = root / "secure.db"
    vulnerable_path = root / "vulnerable.db"

    secure_server = _serve(create_secure_app(Settings(database_path=secure_path)))
    vulnerable_server = _serve(
        create_vulnerable_app(
            Settings(database_path=vulnerable_path, allow_vulnerable_demo=True),
        ),
    )

    # Attach the recorder only after both lifespans have configured logging, so neither clears it.
    handler = RecordingHandler()
    logging.getLogger(LOGGER_NAME).addHandler(handler)

    with (
        httpx.Client(base_url=f"http://127.0.0.1:{secure_server.port}", timeout=10.0) as secure,
        httpx.Client(
            base_url=f"http://127.0.0.1:{vulnerable_server.port}",
            timeout=10.0,
        ) as vulnerable,
    ):
        yield _Stack(
            secure=LoopbackService(
                client=secure,
                engine=create_database_engine(secure_path),
                logs=handler,
            ),
            vulnerable=LoopbackService(
                client=vulnerable,
                engine=create_database_engine(vulnerable_path),
                logs=handler,
            ),
        )

    logging.getLogger(LOGGER_NAME).removeHandler(handler)
    for running in (secure_server, vulnerable_server):
        running.server.should_exit = True
        running.thread.join(timeout=SERVER_START_TIMEOUT_SECONDS)


@pytest.fixture(scope="session")
def service(_stack: _Stack) -> LoopbackService:
    """The secure service."""
    return _stack.secure


@pytest.fixture(scope="session")
def vulnerable_service(_stack: _Stack) -> LoopbackService:
    """The intentionally vulnerable service."""
    return _stack.vulnerable


@pytest.fixture(autouse=True)
def _fresh_state(_stack: _Stack) -> Iterator[None]:
    """Start every case from the same disposable fixture in both variants, and no captured logs."""
    set_pre_commit_hook(None)
    reset_state(_stack.secure.engine)
    reset_state(_stack.vulnerable.engine)
    _stack.secure.logs.reset()
    yield
    set_pre_commit_hook(None)
