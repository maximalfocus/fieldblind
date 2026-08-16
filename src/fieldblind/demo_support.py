"""Pieces both demonstration variants share: correlation, generic failures, and the demo boundary.

Keeping these identical is what makes the comparison honest. The two variants differ only at the
property-authorization boundary; everything around it — credentials, the object policy, the failure
contract, the state boundary — is literally the same code.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import APIRouter, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from fieldblind.domain import DEMO_LABEL
from fieldblind.errors import (
    ERROR_INVALID_REQUEST,
    STATUS_NOT_FOUND,
    STATUS_UNAUTHORIZED,
    generic_error,
    invalid_request,
    not_found,
    unauthorized,
)
from fieldblind.observability import (
    bind_request_id,
    log_request_completed,
    new_request_id,
)
from fieldblind.persistence import load_claim, reset_state
from fieldblind.projections import canonical_state

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from sqlalchemy.engine import Engine
    from sqlalchemy.orm import Session, sessionmaker
    from starlette.responses import Response


def install_request_correlation(app: FastAPI) -> None:
    """Give every request a correlation identifier and one contentless access-log line."""

    @app.middleware("http")
    async def correlate_and_log(
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        bind_request_id(new_request_id())
        response = await call_next(request)
        log_request_completed(request.method, response.status_code)
        return response


def install_generic_error_handlers(app: FastAPI) -> None:
    """Make every framework-generated failure use the same generic shape."""

    @app.exception_handler(StarletteHTTPException)
    async def handle_http_exception(_request: Request, exc: StarletteHTTPException) -> JSONResponse:
        if exc.status_code == STATUS_UNAUTHORIZED:
            return unauthorized()
        if exc.status_code == STATUS_NOT_FOUND:
            return not_found()
        return generic_error(exc.status_code, ERROR_INVALID_REQUEST)

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(
        _request: Request,
        _exc: RequestValidationError,
    ) -> JSONResponse:
        return invalid_request()


def create_demo_router(engine: Engine, session_factory: sessionmaker[Session]) -> APIRouter:
    """Build the demonstration boundary shared by both variants.

    These routes are instrumentation, not product surface. `/demo/state` is the documented stand-in
    for looking at the database, and `/demo/reset` is the disposable-fixture reset the local
    walkthrough uses. Neither takes part in the authorization contract under test, and neither is
    reachable from anywhere but this local demo workflow.
    """
    router = APIRouter()

    @router.get("/healthz")
    def healthz() -> JSONResponse:
        return JSONResponse(content={"status": "ok", "label": DEMO_LABEL})

    @router.get("/demo/state/{claim_id}")
    def demo_state(claim_id: str) -> JSONResponse:
        with session_factory() as session:
            claim = load_claim(session, claim_id)
            if claim is None:
                return not_found()
            return JSONResponse(content={"label": DEMO_LABEL, "claim": canonical_state(claim)})

    @router.post("/demo/reset")
    def demo_reset() -> JSONResponse:
        reset_state(engine)
        return JSONResponse(content={"label": DEMO_LABEL, "reset": True})

    return router
