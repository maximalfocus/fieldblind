"""The write-side flaw: whole-object binding lets an employee decide their own claim."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from fieldblind.domain import CLAIM_FIXTURE
from tests.support import CLAIM_PATH, NIKO_TOKEN, auth, canonical_claim, canonical_text

if TYPE_CHECKING:
    from tests.conftest import LoopbackService

NEW_PURPOSE = "Team offsite ferry catering (revised)"

MIXED_BODY: dict[str, Any] = {
    "purpose": NEW_PURPOSE,
    "decision": "approved",
    "approved_amount_cents": 8640,
}


def test_the_mixed_body_is_accepted(vulnerable_service: LoopbackService) -> None:
    response = vulnerable_service.client.patch(
        CLAIM_PATH,
        headers=auth(NIKO_TOKEN),
        json=MIXED_BODY,
    )
    assert response.status_code == 200


def test_the_employee_changed_the_reviewer_decision_and_amount(
    vulnerable_service: LoopbackService,
) -> None:
    """This is the impact: the claim's own owner approved it, and set the payout."""
    before = canonical_claim(vulnerable_service.client)
    assert before["decision"] == CLAIM_FIXTURE.decision
    assert before["approved_amount_cents"] is None

    vulnerable_service.client.patch(CLAIM_PATH, headers=auth(NIKO_TOKEN), json=MIXED_BODY)

    after = canonical_claim(vulnerable_service.client)
    changed = {name for name in after if after[name] != before[name]}
    assert changed == {"purpose", "decision", "approved_amount_cents"}
    assert after["purpose"] == NEW_PURPOSE
    assert after["decision"] == "approved"
    assert after["approved_amount_cents"] == 8640


def test_the_identical_body_is_refused_by_the_secure_service(
    service: LoopbackService,
) -> None:
    """Same actor, same object, same bytes — the property contract is the only difference."""
    before = canonical_text(service.client)
    response = service.client.patch(CLAIM_PATH, headers=auth(NIKO_TOKEN), json=MIXED_BODY)
    assert response.status_code == 400
    assert canonical_text(service.client) == before


def test_the_vulnerable_response_confirms_the_mutation(
    vulnerable_service: LoopbackService,
) -> None:
    payload = vulnerable_service.client.patch(
        CLAIM_PATH,
        headers=auth(NIKO_TOKEN),
        json=MIXED_BODY,
    ).json()
    assert payload["decision"] == "approved"
    assert payload["approved_amount_cents"] == 8640


def test_reviewer_only_properties_are_individually_bindable(
    vulnerable_service: LoopbackService,
) -> None:
    """No reviewer-only property is protected — the mixed body is just the memorable case."""
    before = canonical_claim(vulnerable_service.client)
    vulnerable_service.client.patch(
        CLAIM_PATH,
        headers=auth(NIKO_TOKEN),
        json={"risk_score": 0, "reviewer_note": "looks fine to me"},
    )
    after = canonical_claim(vulnerable_service.client)
    assert after["risk_score"] == 0
    assert after["reviewer_note"] == "looks fine to me"
    assert before["risk_score"] != after["risk_score"]


def test_an_unknown_key_is_ignored_rather_than_stored(
    vulnerable_service: LoopbackService,
) -> None:
    """The binder reaches the persistence model, not arbitrary storage."""
    before = canonical_claim(vulnerable_service.client)
    vulnerable_service.client.patch(
        CLAIM_PATH,
        headers=auth(NIKO_TOKEN),
        json={"not_a_claim_property": "x"},
    )
    assert canonical_claim(vulnerable_service.client) == before


def test_a_malformed_body_is_still_refused(vulnerable_service: LoopbackService) -> None:
    before = canonical_text(vulnerable_service.client)
    response = vulnerable_service.client.patch(
        CLAIM_PATH,
        headers={**auth(NIKO_TOKEN), "Content-Type": "application/json"},
        content=b"not json",
    )
    assert response.status_code == 400
    assert canonical_text(vulnerable_service.client) == before
