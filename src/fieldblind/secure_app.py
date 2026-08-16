"""The secure demonstration service.

Request order is deliberate and identical for both demonstration variants:

1. resolve the actor server-side from the bearer credential;
2. apply the shared object-level policy;
3. only then choose an actor-specific property contract.

Steps 1 and 2 disclose nothing about the object's properties, so a caller who fails them learns
nothing at all.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, Final

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from fieldblind.authentication import resolve_actor
from fieldblind.config import Settings
from fieldblind.domain import DEMO_LABEL, Role
from fieldblind.errors import (
    ERROR_INVALID_REQUEST,
    STATUS_NOT_FOUND,
    STATUS_UNAUTHORIZED,
    generic_error,
    internal_error,
    invalid_request,
    not_found,
    unauthorized,
)
from fieldblind.object_policy import may_access_claim
from fieldblind.observability import (
    bind_request_id,
    configure_logging,
    log_property_update_rejected,
    log_request_completed,
    new_request_id,
)
from fieldblind.persistence import (
    create_database_engine,
    create_session_factory,
    load_claim,
    reset_state,
)
from fieldblind.projections import canonical_state, employee_projection, reviewer_projection
from fieldblind.service import (
    UpdateRejectedError,
    apply_employee_update,
    apply_reviewer_update,
    parse_update_body,
    validate_employee_update,
    validate_reviewer_update,
)

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Awaitable, Callable

    from starlette.responses import Response

SERVICE_TITLE: Final = "fieldblind secure claim service"


def create_secure_app(settings: Settings | None = None) -> FastAPI:
    """Build the secure service over one disposable SQLite database."""
    resolved = settings if settings is not None else Settings.from_environment()
    engine = create_database_engine(resolved.database_path)
    session_factory = create_session_factory(engine)

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        configure_logging()
        reset_state(engine)
        yield

    app = FastAPI(
        title=SERVICE_TITLE,
        lifespan=lifespan,
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )

    @app.middleware("http")
    async def correlate_and_log(
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        bind_request_id(new_request_id())
        response = await call_next(request)
        log_request_completed(request.method, response.status_code)
        return response

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

    @app.get("/healthz")
    def healthz() -> JSONResponse:
        return JSONResponse(content={"status": "ok", "label": DEMO_LABEL})

    @app.get("/demo/state/{claim_id}")
    def demo_state(claim_id: str) -> JSONResponse:
        """Return the full canonical state.

        This is the documented demonstration boundary. It stands in for looking at the database so
        the walkthrough and the tests can prove byte-for-byte state without reading SQLite, and it
        takes no part in the authorization contract under test.
        """
        with session_factory() as session:
            claim = load_claim(session, claim_id)
            if claim is None:
                return not_found()
            return JSONResponse(content={"label": DEMO_LABEL, "claim": canonical_state(claim)})

    @app.get("/claims/{claim_id}")
    def read_claim(claim_id: str, request: Request) -> JSONResponse:
        actor = resolve_actor(request.headers.get("authorization"))
        if actor is None:
            return unauthorized()
        with session_factory() as session:
            claim = load_claim(session, claim_id)
            if claim is None or not may_access_claim(actor, claim):
                return not_found()
            if actor.role is Role.REVIEWER:
                return JSONResponse(content=reviewer_projection(claim).model_dump(mode="json"))
            return JSONResponse(content=employee_projection(claim).model_dump(mode="json"))

    @app.patch("/claims/{claim_id}")
    async def update_claim(claim_id: str, request: Request) -> JSONResponse:
        actor = resolve_actor(request.headers.get("authorization"))
        if actor is None:
            return unauthorized()
        raw = await request.body()
        with session_factory() as session:
            claim = load_claim(session, claim_id)
            if claim is None or not may_access_claim(actor, claim):
                return not_found()
            try:
                payload = parse_update_body(raw)
                if actor.role is Role.REVIEWER:
                    reviewer_update = validate_reviewer_update(payload)
                    apply_reviewer_update(session, claim, reviewer_update)
                    return JSONResponse(content=reviewer_projection(claim).model_dump(mode="json"))
                employee_update = validate_employee_update(payload)
                apply_employee_update(session, claim, employee_update)
            except UpdateRejectedError as rejected:
                session.rollback()
                log_property_update_rejected(actor.actor_id, claim_id, rejected.reason_code)
                return invalid_request()
            except Exception:  # fail closed, roll back, and disclose nothing
                session.rollback()
                return internal_error()
            return JSONResponse(content=employee_projection(claim).model_dump(mode="json"))

    return app
