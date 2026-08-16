"""Explicit claim projections.

Each function below names every property it emits. A stored property that is not named here cannot
reach a caller, which is what makes the property policy deny-by-default rather than best-effort.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from fieldblind.schemas import EmployeeClaimResponse, ReviewerClaimResponse

if TYPE_CHECKING:
    from fieldblind.persistence import ClaimRecord


def employee_projection(claim: ClaimRecord) -> EmployeeClaimResponse:
    """Project the claim for an authorized employee, omitting every reviewer-only property."""
    return EmployeeClaimResponse(
        claim_id=claim.claim_id,
        employee_id=claim.employee_id,
        merchant=claim.merchant,
        amount_cents=claim.amount_cents,
        purpose=claim.purpose,
        status=claim.status,
        submitted_on=claim.submitted_on,
    )


def reviewer_projection(claim: ClaimRecord) -> ReviewerClaimResponse:
    """Project the claim for the reviewer, including the properties needed to decide it."""
    return ReviewerClaimResponse(
        claim_id=claim.claim_id,
        employee_id=claim.employee_id,
        merchant=claim.merchant,
        amount_cents=claim.amount_cents,
        purpose=claim.purpose,
        status=claim.status,
        submitted_on=claim.submitted_on,
        risk_score=claim.risk_score,
        reviewer_note=claim.reviewer_note,
        decision=claim.decision,
        approved_amount_cents=claim.approved_amount_cents,
    )


def canonical_state(claim: ClaimRecord) -> dict[str, object]:
    """Return the full canonical claim state in a stable order.

    This is the demonstration boundary only. It is the documented stand-in for looking at the
    database, it is not part of the authorization contract, and no authorization decision consults
    it.
    """
    return {
        "claim_id": claim.claim_id,
        "employee_id": claim.employee_id,
        "merchant": claim.merchant,
        "amount_cents": claim.amount_cents,
        "purpose": claim.purpose,
        "status": claim.status,
        "submitted_on": claim.submitted_on,
        "risk_score": claim.risk_score,
        "reviewer_note": claim.reviewer_note,
        "decision": claim.decision,
        "approved_amount_cents": claim.approved_amount_cents,
    }
