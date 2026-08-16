"""The generic client-facing failure contract.

Every refusal returns the same fixed shape. Nothing in it says which property was submitted, whether
a property exists, whether it is internal, or whether it is reviewer-only.
"""

from __future__ import annotations

from typing import Final

from fastapi.responses import JSONResponse

from fieldblind.observability import current_request_id

ERROR_UNAUTHORIZED: Final = "unauthorized"
ERROR_NOT_FOUND: Final = "not_found"
ERROR_INVALID_REQUEST: Final = "invalid_request"
ERROR_INTERNAL: Final = "internal_error"

STATUS_OK: Final = 200
STATUS_UNAUTHORIZED: Final = 401
STATUS_NOT_FOUND: Final = 404
STATUS_INVALID_REQUEST: Final = 400
STATUS_INTERNAL: Final = 500


def generic_error(status_code: int, error: str) -> JSONResponse:
    """Build one generic failure response carrying only its code and the correlation identifier."""
    return JSONResponse(
        status_code=status_code,
        content={"error": error, "request_id": current_request_id()},
    )


def unauthorized() -> JSONResponse:
    """One uniform response for a missing, malformed, or unknown credential."""
    return generic_error(STATUS_UNAUTHORIZED, ERROR_UNAUTHORIZED)


def not_found() -> JSONResponse:
    """One uniform response for an unknown claim and for a claim the actor may not access."""
    return generic_error(STATUS_NOT_FOUND, ERROR_NOT_FOUND)


def invalid_request() -> JSONResponse:
    """One uniform response for every refused update, whatever the internal reason was."""
    return generic_error(STATUS_INVALID_REQUEST, ERROR_INVALID_REQUEST)


def internal_error() -> JSONResponse:
    """One uniform response for an unexpected server-side failure."""
    return generic_error(STATUS_INTERNAL, ERROR_INTERNAL)
