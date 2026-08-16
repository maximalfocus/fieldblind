"""The intentionally vulnerable demonstration service. Local, fictional, and opt-in only.

**This service is deliberately broken. Never run it anywhere but this local demo.**

It is byte-for-byte the same product as the secure service — same credentials, same object policy,
same domain model, same fixture, same failure contract — except at the property-authorization
boundary, where it does the two things this project exists to teach against:

* **the read-side flaw (`FR-010`)** — it serializes the whole stored claim object generically, with
  no property policy, so an employee who legitimately owns the claim also receives every
  reviewer-only property; and
* **the write-side flaw (`FR-011`)** — it binds client-supplied keys onto the stored object
  generically, so an employee can set reviewer-only properties by naming them in an ordinary update.

Both flaws are confined to this file, reachable only through this service's own local endpoint, and
require two explicit opt-in actions to start. There is no property enumerator, wordlist, schema
fuzzer, arbitrary target, proxy, or reusable extraction tool here or anywhere in this project.
"""

from __future__ import annotations

import json
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, Any, Final

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from sqlalchemy import inspect

from fieldblind.authentication import resolve_actor
from fieldblind.config import ALLOW_VULNERABLE_VALUE, ALLOW_VULNERABLE_VARIABLE, Settings
from fieldblind.demo_support import (
    create_demo_router,
    install_generic_error_handlers,
    install_request_correlation,
)
from fieldblind.errors import internal_error, invalid_request, not_found, unauthorized
from fieldblind.object_policy import may_access_claim
from fieldblind.observability import configure_logging
from fieldblind.persistence import (
    ClaimRecord,
    create_database_engine,
    create_session_factory,
    load_claim,
    reset_state,
)

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

SERVICE_TITLE: Final = "fieldblind INTENTIONALLY VULNERABLE claim service"

#: Skipped by the generic binder so the fixed fixture stays addressable for the walkthrough.
#: This is not an authorization control, and it protects no reviewer-only property: every property
#: this demonstration is about remains fully bindable below.
_IDENTITY_COLUMN: Final = "claim_id"


class VulnerableDemoNotEnabledError(RuntimeError):
    """Raised when the vulnerable service is started without its explicit opt-in."""

    def __init__(self) -> None:
        super().__init__(
            f"refusing to start: set {ALLOW_VULNERABLE_VARIABLE}={ALLOW_VULNERABLE_VALUE} and use "
            f"the 'vulnerable' Compose profile to run the intentionally vulnerable demo service",
        )


def _claim_columns() -> list[str]:
    return list(inspect(ClaimRecord).columns.keys())


def serialize_whole_object(claim: ClaimRecord) -> dict[str, Any]:
    """THE READ-SIDE FLAW: turn the entire stored object into the response.

    The object-level check already passed, and this function asks no further question. Whatever the
    persistence model holds — including every reviewer-only property — goes straight to the caller.
    The secure service answers the same request from an explicit per-actor response schema instead.
    """
    return {name: getattr(claim, name) for name in _claim_columns()}


def bind_whole_object(claim: ClaimRecord, payload: dict[str, Any]) -> None:
    """THE WRITE-SIDE FLAW: assign every submitted key that happens to match a stored property.

    The object-level check already passed, so this treats "may touch the claim" as "may set any
    property on the claim". A body that mixes one authorized edit with reviewer-only keys is applied
    in full. The secure service validates the same body against an explicit per-actor request schema
    and refuses the whole request instead.
    """
    bindable = set(_claim_columns()) - {_IDENTITY_COLUMN}
    for key, value in payload.items():
        if key in bindable:
            setattr(claim, key, value)


def create_vulnerable_app(settings: Settings | None = None) -> FastAPI:
    """Build the intentionally vulnerable service, refusing to start without the explicit opt-in."""
    resolved = settings if settings is not None else Settings.from_environment()
    if not resolved.allow_vulnerable_demo:
        raise VulnerableDemoNotEnabledError
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
    install_request_correlation(app)
    install_generic_error_handlers(app)
    app.include_router(create_demo_router(engine, session_factory))

    @app.get("/claims/{claim_id}")
    def read_claim(claim_id: str, request: Request) -> JSONResponse:
        actor = resolve_actor(request.headers.get("authorization"))
        if actor is None:
            return unauthorized()
        with session_factory() as session:
            claim = load_claim(session, claim_id)
            if claim is None or not may_access_claim(actor, claim):
                return not_found()
            # Same actor, same object verdict as the secure service — and then no property policy.
            return JSONResponse(content=serialize_whole_object(claim))

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
                payload = json.loads(raw)
            except (json.JSONDecodeError, UnicodeDecodeError):
                return invalid_request()
            if not isinstance(payload, dict):
                return invalid_request()
            try:
                bind_whole_object(claim, payload)
                session.commit()
            except Exception:  # a broken demo service still must not corrupt its own state
                session.rollback()
                return internal_error()
            return JSONResponse(content=serialize_whole_object(claim))

    return app
