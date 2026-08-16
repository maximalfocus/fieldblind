"""Bounded JSON logging, request correlation, and the single audit event contract.

Two rules hold everywhere in this module:

* every emitted field name comes from a fixed allowlist, and
* no credential, request body, property name, or property value is ever a value.
"""

from __future__ import annotations

import json
import logging
import sys
import uuid
from contextvars import ContextVar
from typing import Final

LOGGER_NAME: Final = "fieldblind"

_logger: Final = logging.getLogger(LOGGER_NAME)
_request_id: ContextVar[str] = ContextVar("fieldblind_request_id", default="-")

#: The only event names this service emits.
EVENT_REQUEST_COMPLETED: Final = "request_completed"
EVENT_PROPERTY_UPDATE_REJECTED: Final = "property_update_rejected"

EVENT_NAMES: Final[frozenset[str]] = frozenset(
    {EVENT_REQUEST_COMPLETED, EVENT_PROPERTY_UPDATE_REJECTED},
)

#: The only field names any event may carry. Property names and values are absent by construction.
EVENT_FIELDS: Final[frozenset[str]] = frozenset(
    {"event", "request_id", "actor_id", "object_id", "outcome", "reason_code", "method", "status"},
)

#: The bounded internal reason codes an audit event may report.
REASON_MALFORMED_BODY: Final = "malformed_body"
REASON_DUPLICATE_PROPERTY: Final = "duplicate_property"
REASON_SCHEMA_REJECTED: Final = "schema_rejected"
REASON_INVALID_VALUE: Final = "invalid_value"

REASON_CODES: Final[frozenset[str]] = frozenset(
    {
        REASON_MALFORMED_BODY,
        REASON_DUPLICATE_PROPERTY,
        REASON_SCHEMA_REJECTED,
        REASON_INVALID_VALUE,
    },
)


class _JsonFormatter(logging.Formatter):
    """Render each record as the single JSON object the event builder already produced."""

    def format(self, record: logging.LogRecord) -> str:
        return record.getMessage()


def configure_logging() -> None:
    """Send bounded JSON events to stdout exactly once per process."""
    _logger.handlers.clear()
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(_JsonFormatter())
    _logger.addHandler(handler)
    _logger.setLevel(logging.INFO)
    _logger.propagate = False


def new_request_id() -> str:
    """Generate the correlation identifier for one request."""
    return str(uuid.uuid4())


def bind_request_id(request_id: str) -> None:
    """Bind the correlation identifier for the current request context."""
    _request_id.set(request_id)


def current_request_id() -> str:
    """Return the correlation identifier bound to the current request context."""
    return _request_id.get()


def _emit(payload: dict[str, str | int]) -> None:
    unknown = set(payload) - EVENT_FIELDS
    if unknown:
        message = f"refusing to log unknown event fields: {sorted(unknown)}"
        raise ValueError(message)
    _logger.info(json.dumps(payload, separators=(",", ":")))


def log_request_completed(method: str, status: int) -> None:
    """Record one ordinary access-log line. It carries no body, credential, or property."""
    _emit(
        {
            "event": EVENT_REQUEST_COMPLETED,
            "request_id": current_request_id(),
            "method": method,
            "status": status,
        },
    )


def log_property_update_rejected(actor_id: str, object_id: str, reason_code: str) -> None:
    """Record the single audit event for one refused property update."""
    if reason_code not in REASON_CODES:
        message = f"unbounded audit reason code: {reason_code}"
        raise ValueError(message)
    _emit(
        {
            "event": EVENT_PROPERTY_UPDATE_REJECTED,
            "request_id": current_request_id(),
            "actor_id": actor_id,
            "object_id": object_id,
            "outcome": "rejected",
            "reason_code": reason_code,
        },
    )
