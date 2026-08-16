"""Actor-specific request and response contracts.

Every model here enumerates its properties by hand and forbids unknown keys. None of them is built
from the persistence model, so a new stored column cannot become readable or writable by accident.
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, StringConstraints, field_validator

from fieldblind.domain import DECISION_APPROVED, DECISION_REJECTED

_PUBLIC_MODEL_CONFIG = ConfigDict(extra="forbid", strict=True, frozen=True)

Purpose = Annotated[str, StringConstraints(min_length=1, max_length=120)]


class EmployeeClaimResponse(BaseModel):
    """What an authorized employee may read. The reviewer-only properties are absent by name."""

    model_config = _PUBLIC_MODEL_CONFIG

    claim_id: str
    employee_id: str
    merchant: str
    amount_cents: int
    purpose: str
    status: str
    submitted_on: str


class ReviewerClaimResponse(BaseModel):
    """What a reviewer may read: the employee view plus the properties needed to decide."""

    model_config = _PUBLIC_MODEL_CONFIG

    claim_id: str
    employee_id: str
    merchant: str
    amount_cents: int
    purpose: str
    status: str
    submitted_on: str
    risk_score: int
    reviewer_note: str
    decision: str
    approved_amount_cents: int | None


class EmployeeClaimUpdate(BaseModel):
    """The only update an employee may submit."""

    model_config = _PUBLIC_MODEL_CONFIG

    purpose: Purpose

    @field_validator("purpose")
    @classmethod
    def reject_blank_purpose(cls, value: str) -> str:
        """Refuse a purpose made only of whitespace."""
        if not value.strip():
            message = "purpose must not be blank"
            raise ValueError(message)
        return value


class ReviewerClaimUpdate(BaseModel):
    """The only update a reviewer may submit."""

    model_config = _PUBLIC_MODEL_CONFIG

    decision: Literal["approved", "rejected"]
    approved_amount_cents: int | None = None

    @field_validator("approved_amount_cents")
    @classmethod
    def reject_negative_amount(cls, value: int | None) -> int | None:
        """Refuse a negative approved amount."""
        if value is not None and value < 0:
            message = "approved_amount_cents must not be negative"
            raise ValueError(message)
        return value


#: Frozen key sets. The structural suite fails if a contract ever drifts away from these.
EMPLOYEE_RESPONSE_KEYS: frozenset[str] = frozenset(EmployeeClaimResponse.model_fields)
REVIEWER_RESPONSE_KEYS: frozenset[str] = frozenset(ReviewerClaimResponse.model_fields)
EMPLOYEE_UPDATE_KEYS: frozenset[str] = frozenset(EmployeeClaimUpdate.model_fields)
REVIEWER_UPDATE_KEYS: frozenset[str] = frozenset(ReviewerClaimUpdate.model_fields)

DECISION_VALUES: frozenset[str] = frozenset({DECISION_APPROVED, DECISION_REJECTED})
