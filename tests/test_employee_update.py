"""Write-side property authorization for the employee contract."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest

from fieldblind.domain import CLAIM_FIXTURE, REVIEWER_ONLY_PROPERTIES
from tests.support import CLAIM_PATH, NIKO_TOKEN, auth, canonical_claim, canonical_text

if TYPE_CHECKING:
    from tests.conftest import LoopbackService

NEW_PURPOSE = "Team offsite ferry catering (revised)"

MIXED_BODY: dict[str, Any] = {
    "purpose": NEW_PURPOSE,
    "decision": "approved",
    "approved_amount_cents": 8640,
}

FORBIDDEN_BODIES = [
    pytest.param({}, id="empty-object"),
    pytest.param({"decision": "approved"}, id="reviewer-only-key"),
    pytest.param({"approved_amount_cents": 8640}, id="reviewer-only-amount"),
    pytest.param({"risk_score": 0}, id="reviewer-only-risk"),
    pytest.param({"reviewer_note": "cleared"}, id="reviewer-only-note"),
    pytest.param({"claim_id": "EXP-999"}, id="read-only-identifier"),
    pytest.param({"employee_id": "uma"}, id="read-only-owner"),
    pytest.param({"amount_cents": 1}, id="read-only-amount"),
    pytest.param({"status": "approved"}, id="read-only-status"),
    pytest.param({"submitted_on": "2026-01-01"}, id="read-only-date"),
    pytest.param({"unknown_property": "x"}, id="unknown-key"),
    pytest.param({"purpose": ""}, id="empty-purpose"),
    pytest.param({"purpose": "   "}, id="blank-purpose"),
    pytest.param({"purpose": 7}, id="wrong-type"),
    pytest.param({"purpose": None}, id="null-purpose"),
    pytest.param({"purpose": "x" * 121}, id="oversized-purpose"),
    pytest.param(MIXED_BODY, id="mixed-authorized-and-forbidden"),
]


def test_authorized_purpose_edit_is_accepted(service: LoopbackService) -> None:
    response = service.client.patch(
        CLAIM_PATH,
        headers=auth(NIKO_TOKEN),
        json={"purpose": NEW_PURPOSE},
    )
    assert response.status_code == 200
    assert response.json()["purpose"] == NEW_PURPOSE


def test_authorized_purpose_edit_changes_only_that_property(service: LoopbackService) -> None:
    before = canonical_claim(service.client)
    service.client.patch(CLAIM_PATH, headers=auth(NIKO_TOKEN), json={"purpose": NEW_PURPOSE})
    after = canonical_claim(service.client)
    assert after["purpose"] == NEW_PURPOSE
    changed = {name for name in after if after[name] != before[name]}
    assert changed == {"purpose"}


def test_authorized_edit_response_still_hides_reviewer_only_properties(
    service: LoopbackService,
) -> None:
    response = service.client.patch(
        CLAIM_PATH,
        headers=auth(NIKO_TOKEN),
        json={"purpose": NEW_PURPOSE},
    )
    for name in REVIEWER_ONLY_PROPERTIES:
        assert name not in response.text


@pytest.mark.parametrize("body", FORBIDDEN_BODIES)
def test_forbidden_employee_body_is_refused_generically(
    service: LoopbackService,
    body: dict[str, Any],
) -> None:
    response = service.client.patch(CLAIM_PATH, headers=auth(NIKO_TOKEN), json=body)
    assert response.status_code == 400
    assert set(response.json()) == {"error", "request_id"}
    assert response.json()["error"] == "invalid_request"


@pytest.mark.parametrize("body", FORBIDDEN_BODIES)
def test_forbidden_employee_body_preserves_state(
    service: LoopbackService,
    body: dict[str, Any],
) -> None:
    before = canonical_text(service.client)
    service.client.patch(CLAIM_PATH, headers=auth(NIKO_TOKEN), json=body)
    assert canonical_text(service.client) == before


@pytest.mark.parametrize("body", FORBIDDEN_BODIES)
def test_rejection_names_no_submitted_or_protected_property(
    service: LoopbackService,
    body: dict[str, Any],
) -> None:
    response = service.client.patch(CLAIM_PATH, headers=auth(NIKO_TOKEN), json=body)
    for name in body:
        assert name not in response.text
    for name in REVIEWER_ONLY_PROPERTIES:
        assert name not in response.text


def test_mixed_body_does_not_partially_apply_the_authorized_edit(
    service: LoopbackService,
) -> None:
    """The whole request is refused: even the legitimate `purpose` edit does not land."""
    before = canonical_text(service.client)
    response = service.client.patch(CLAIM_PATH, headers=auth(NIKO_TOKEN), json=MIXED_BODY)
    assert response.status_code == 400
    after = canonical_claim(service.client)
    assert after["purpose"] == CLAIM_FIXTURE.purpose
    assert after["decision"] == CLAIM_FIXTURE.decision
    assert after["approved_amount_cents"] == CLAIM_FIXTURE.approved_amount_cents
    assert canonical_text(service.client) == before


@pytest.mark.parametrize(
    "raw",
    [
        pytest.param(b"", id="empty-body"),
        pytest.param(b"not json", id="not-json"),
        pytest.param(b"[]", id="json-array"),
        pytest.param(b'"purpose"', id="json-string"),
        pytest.param(b"null", id="json-null"),
        pytest.param(b'{"purpose": "a"', id="truncated-object"),
    ],
)
def test_malformed_body_is_refused_and_preserves_state(
    service: LoopbackService,
    raw: bytes,
) -> None:
    before = canonical_text(service.client)
    response = service.client.patch(
        CLAIM_PATH,
        headers={**auth(NIKO_TOKEN), "Content-Type": "application/json"},
        content=raw,
    )
    assert response.status_code == 400
    assert canonical_text(service.client) == before


def test_duplicate_property_is_refused(service: LoopbackService) -> None:
    """A repeated key is ambiguous, so the whole body fails closed."""
    before = canonical_text(service.client)
    response = service.client.patch(
        CLAIM_PATH,
        headers={**auth(NIKO_TOKEN), "Content-Type": "application/json"},
        content=b'{"purpose": "first", "purpose": "second"}',
    )
    assert response.status_code == 400
    assert canonical_text(service.client) == before
