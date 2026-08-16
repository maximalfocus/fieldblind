"""Strict body parsing, actor-specific validation, and explicit transactional assignment.

Nothing in this module spreads, unpacks, or iterates caller-supplied key/value pairs into
persistence state. Each accepted property is assigned by name.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from pydantic import ValidationError

from fieldblind.domain import DECISION_APPROVED
from fieldblind.observability import (
    REASON_DUPLICATE_PROPERTY,
    REASON_INVALID_VALUE,
    REASON_MALFORMED_BODY,
    REASON_SCHEMA_REJECTED,
)
from fieldblind.schemas import EmployeeClaimUpdate, ReviewerClaimUpdate

if TYPE_CHECKING:
    from collections.abc import Callable

    from sqlalchemy.orm import Session

    from fieldblind.persistence import ClaimRecord


class UpdateRejectedError(Exception):
    """Raised when an update is refused before any domain mutation happens."""

    def __init__(self, reason_code: str) -> None:
        super().__init__(reason_code)
        self.reason_code = reason_code


class _DuplicatePropertyError(Exception):
    """Internal signal that the raw body repeated a key."""


@dataclass(slots=True)
class _TestSeam:
    """In-process hook used by the test suite to inject a pre-commit failure.

    It is deliberately not reachable from any request: there is no header, query parameter, or
    endpoint that sets it.
    """

    pre_commit: Callable[[], None] | None = None


_SEAM = _TestSeam()


def set_pre_commit_hook(hook: Callable[[], None] | None) -> None:
    """Install or clear the in-process pre-commit failure hook."""
    _SEAM.pre_commit = hook


def _run_pre_commit_hook() -> None:
    hook = _SEAM.pre_commit
    if hook is not None:
        hook()


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    seen: set[str] = set()
    for key, _value in pairs:
        if key in seen:
            raise _DuplicatePropertyError
        seen.add(key)
    return dict(pairs)


def parse_update_body(raw: bytes) -> dict[str, Any]:
    """Parse the raw request body into a JSON object, failing closed on anything else."""
    if not raw:
        raise UpdateRejectedError(REASON_MALFORMED_BODY)
    try:
        parsed = json.loads(raw, object_pairs_hook=_reject_duplicate_keys)
    except _DuplicatePropertyError:
        raise UpdateRejectedError(REASON_DUPLICATE_PROPERTY) from None
    except (json.JSONDecodeError, UnicodeDecodeError):
        raise UpdateRejectedError(REASON_MALFORMED_BODY) from None
    if not isinstance(parsed, dict):
        raise UpdateRejectedError(REASON_MALFORMED_BODY)
    return parsed


def validate_employee_update(payload: dict[str, Any]) -> EmployeeClaimUpdate:
    """Validate an employee body against the employee-only contract."""
    try:
        return EmployeeClaimUpdate.model_validate(payload)
    except ValidationError:
        raise UpdateRejectedError(REASON_SCHEMA_REJECTED) from None


def validate_reviewer_update(payload: dict[str, Any]) -> ReviewerClaimUpdate:
    """Validate a reviewer body against the reviewer-only contract."""
    try:
        return ReviewerClaimUpdate.model_validate(payload)
    except ValidationError:
        raise UpdateRejectedError(REASON_SCHEMA_REJECTED) from None


def _check_reviewer_invariants(claim: ClaimRecord, update: ReviewerClaimUpdate) -> None:
    if update.decision == DECISION_APPROVED:
        if update.approved_amount_cents is None:
            raise UpdateRejectedError(REASON_INVALID_VALUE)
        if update.approved_amount_cents > claim.amount_cents:
            raise UpdateRejectedError(REASON_INVALID_VALUE)
    elif update.approved_amount_cents is not None:
        raise UpdateRejectedError(REASON_INVALID_VALUE)


def apply_employee_update(
    session: Session,
    claim: ClaimRecord,
    update: EmployeeClaimUpdate,
) -> None:
    """Assign the one employee-writable property inside a single transaction."""
    try:
        claim.purpose = update.purpose
        _run_pre_commit_hook()
        session.commit()
    except Exception:
        session.rollback()
        raise


def apply_reviewer_update(
    session: Session,
    claim: ClaimRecord,
    update: ReviewerClaimUpdate,
) -> None:
    """Assign the reviewer-writable properties inside a single transaction."""
    _check_reviewer_invariants(claim, update)
    try:
        claim.decision = update.decision
        claim.approved_amount_cents = update.approved_amount_cents
        _run_pre_commit_hook()
        session.commit()
    except Exception:
        session.rollback()
        raise
