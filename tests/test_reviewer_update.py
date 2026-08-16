"""Write-side property authorization for the reviewer contract."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest

from fieldblind.domain import CLAIM_FIXTURE, EMPLOYEE_VISIBLE_PROPERTIES, REVIEWER_ONLY_PROPERTIES
from tests.support import CLAIM_PATH, SOL_TOKEN, auth, canonical_claim, canonical_text

if TYPE_CHECKING:
    from tests.conftest import LoopbackService

APPROVAL: dict[str, Any] = {"decision": "approved", "approved_amount_cents": 8640}

FORBIDDEN_BODIES = [
    pytest.param({}, id="empty-object"),
    pytest.param({"purpose": "reviewer rewrite"}, id="employee-only-key"),
    pytest.param({"decision": "approved", "purpose": "x"}, id="mixed-with-employee-key"),
    pytest.param({"decision": "pending"}, id="unsupported-decision"),
    pytest.param({"decision": "approved"}, id="approval-without-amount"),
    pytest.param({"decision": "approved", "approved_amount_cents": 8641}, id="amount-above-claim"),
    pytest.param({"decision": "approved", "approved_amount_cents": -1}, id="negative-amount"),
    pytest.param({"decision": "rejected", "approved_amount_cents": 100}, id="rejected-with-amount"),
    pytest.param({"approved_amount_cents": 8640}, id="amount-without-decision"),
    pytest.param({"risk_score": 0}, id="reviewer-read-only-key"),
    pytest.param({"unknown_property": "x"}, id="unknown-key"),
]


def test_reviewer_approval_is_accepted(service: LoopbackService) -> None:
    response = service.client.patch(CLAIM_PATH, headers=auth(SOL_TOKEN), json=APPROVAL)
    assert response.status_code == 200
    payload = response.json()
    assert payload["decision"] == "approved"
    assert payload["approved_amount_cents"] == 8640


def test_reviewer_approval_changes_exactly_the_authorized_properties(
    service: LoopbackService,
) -> None:
    before = canonical_claim(service.client)
    service.client.patch(CLAIM_PATH, headers=auth(SOL_TOKEN), json=APPROVAL)
    after = canonical_claim(service.client)
    changed = {name for name in after if after[name] != before[name]}
    assert changed == {"decision", "approved_amount_cents"}


def test_reviewer_rejection_is_accepted(service: LoopbackService) -> None:
    before = canonical_claim(service.client)
    response = service.client.patch(
        CLAIM_PATH,
        headers=auth(SOL_TOKEN),
        json={"decision": "rejected"},
    )
    assert response.status_code == 200
    after = canonical_claim(service.client)
    changed = {name for name in after if after[name] != before[name]}
    assert changed == {"decision"}
    assert after["decision"] == "rejected"


def test_reviewer_update_response_is_the_reviewer_projection(service: LoopbackService) -> None:
    response = service.client.patch(CLAIM_PATH, headers=auth(SOL_TOKEN), json=APPROVAL)
    assert tuple(response.json()) == (*EMPLOYEE_VISIBLE_PROPERTIES, *REVIEWER_ONLY_PROPERTIES)


def test_approval_at_the_claimed_amount_is_permitted(service: LoopbackService) -> None:
    response = service.client.patch(
        CLAIM_PATH,
        headers=auth(SOL_TOKEN),
        json={"decision": "approved", "approved_amount_cents": CLAIM_FIXTURE.amount_cents},
    )
    assert response.status_code == 200


def test_approval_below_the_claimed_amount_is_permitted(service: LoopbackService) -> None:
    response = service.client.patch(
        CLAIM_PATH,
        headers=auth(SOL_TOKEN),
        json={"decision": "approved", "approved_amount_cents": 1},
    )
    assert response.status_code == 200
    assert canonical_claim(service.client)["approved_amount_cents"] == 1


@pytest.mark.parametrize("body", FORBIDDEN_BODIES)
def test_forbidden_reviewer_body_is_refused_generically(
    service: LoopbackService,
    body: dict[str, Any],
) -> None:
    response = service.client.patch(CLAIM_PATH, headers=auth(SOL_TOKEN), json=body)
    assert response.status_code == 400
    assert response.json()["error"] == "invalid_request"


@pytest.mark.parametrize("body", FORBIDDEN_BODIES)
def test_forbidden_reviewer_body_preserves_state(
    service: LoopbackService,
    body: dict[str, Any],
) -> None:
    before = canonical_text(service.client)
    service.client.patch(CLAIM_PATH, headers=auth(SOL_TOKEN), json=body)
    assert canonical_text(service.client) == before


def test_reviewer_cannot_edit_the_employee_property(service: LoopbackService) -> None:
    """Contracts are selected by actor, so the reviewer contract has no `purpose` at all."""
    before = canonical_claim(service.client)
    response = service.client.patch(
        CLAIM_PATH,
        headers=auth(SOL_TOKEN),
        json={"purpose": "reviewer rewrite"},
    )
    assert response.status_code == 400
    assert canonical_claim(service.client)["purpose"] == before["purpose"]
