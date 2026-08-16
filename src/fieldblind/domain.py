"""Fixed fictional actors, credentials, claim fixture, and property sets.

The property sets in this module are the single declaration of *which* properties exist and *who*
may see them. They are enumerated by hand on purpose: a property becomes externally visible only by
being named in an explicit contract, never by being added to the persistence model.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Final

DEMO_LABEL: Final = "FICTIONAL LOCAL DEMO"


class Role(StrEnum):
    """The two demonstration roles."""

    EMPLOYEE = "employee"
    REVIEWER = "reviewer"


@dataclass(frozen=True, slots=True)
class Actor:
    """A resolved, server-side demonstration identity."""

    actor_id: str
    role: Role


NIKO: Final = Actor(actor_id="niko", role=Role.EMPLOYEE)
UMA: Final = Actor(actor_id="uma", role=Role.EMPLOYEE)
SOL: Final = Actor(actor_id="sol", role=Role.REVIEWER)

# Fixed, conspicuously fictional bearer credentials. They are demonstration constants, not secrets:
# the whole product is local, disposable, and carries no real data.
DEMO_CREDENTIALS: Final[dict[str, Actor]] = {
    "fictional-demo-token-niko": NIKO,
    "fictional-demo-token-uma": UMA,
    "fictional-demo-token-sol": SOL,
}

CLAIM_ID: Final = "EXP-204"

#: Properties an authorized employee may read.
EMPLOYEE_VISIBLE_PROPERTIES: Final[tuple[str, ...]] = (
    "claim_id",
    "employee_id",
    "merchant",
    "amount_cents",
    "purpose",
    "status",
    "submitted_on",
)

#: Properties only a reviewer may read. An employee must never learn these names or values.
REVIEWER_ONLY_PROPERTIES: Final[tuple[str, ...]] = (
    "risk_score",
    "reviewer_note",
    "decision",
    "approved_amount_cents",
)

#: Full canonical state in a stable order, used only by the demonstration boundary.
CANONICAL_PROPERTY_ORDER: Final[tuple[str, ...]] = (
    *EMPLOYEE_VISIBLE_PROPERTIES,
    *REVIEWER_ONLY_PROPERTIES,
)

#: The single property an employee may change.
EMPLOYEE_WRITABLE_PROPERTIES: Final[tuple[str, ...]] = ("purpose",)

#: The properties a reviewer may change.
REVIEWER_WRITABLE_PROPERTIES: Final[tuple[str, ...]] = ("decision", "approved_amount_cents")


@dataclass(frozen=True, slots=True)
class ClaimFixture:
    """The one fictional expense claim used by every demonstration case."""

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


CLAIM_FIXTURE: Final = ClaimFixture(
    claim_id=CLAIM_ID,
    employee_id=NIKO.actor_id,
    merchant="Harborlight Ferry Canteen",
    amount_cents=8640,
    purpose="Team offsite ferry catering",
    status="submitted",
    submitted_on="2026-02-11",
    risk_score=73,
    reviewer_note="Second receipt page missing; confirm with the desk lead.",
    decision="pending",
    approved_amount_cents=None,
)

DECISION_PENDING: Final = "pending"
DECISION_APPROVED: Final = "approved"
DECISION_REJECTED: Final = "rejected"
