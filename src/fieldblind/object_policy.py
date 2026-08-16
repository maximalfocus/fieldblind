"""The shared object-level authorization boundary.

Both demonstration variants apply this rule identically and *before* any serialization or update
processing. The deliberate flaw taught by this project sits above this boundary, not inside it.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from fieldblind.domain import Role

if TYPE_CHECKING:
    from fieldblind.domain import Actor
    from fieldblind.persistence import ClaimRecord


def may_access_claim(actor: Actor, claim: ClaimRecord | None) -> bool:
    """Report whether the actor may access this claim at all.

    A reviewer may access any claim. An employee may access only a claim they own. An unknown claim
    and a claim owned by somebody else produce the same answer, so the caller cannot tell them
    apart.
    """
    if claim is None:
        return False
    if actor.role is Role.REVIEWER:
        return True
    return claim.employee_id == actor.actor_id
