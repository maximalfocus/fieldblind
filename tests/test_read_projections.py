"""Read-side property authorization: who sees which properties, and who never learns they exist."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from fieldblind.domain import (
    CLAIM_FIXTURE,
    EMPLOYEE_VISIBLE_PROPERTIES,
    REVIEWER_ONLY_PROPERTIES,
)
from tests.support import CLAIM_PATH, NIKO_TOKEN, SOL_TOKEN, auth

if TYPE_CHECKING:
    from tests.conftest import LoopbackService

REVIEWER_ONLY_VALUES = [
    str(CLAIM_FIXTURE.risk_score),
    CLAIM_FIXTURE.reviewer_note,
    CLAIM_FIXTURE.decision,
]


def test_employee_read_returns_exactly_the_authorized_key_set(service: LoopbackService) -> None:
    response = service.client.get(CLAIM_PATH, headers=auth(NIKO_TOKEN))
    assert response.status_code == 200
    assert tuple(response.json()) == EMPLOYEE_VISIBLE_PROPERTIES


@pytest.mark.parametrize("name", REVIEWER_ONLY_PROPERTIES)
def test_employee_read_hides_reviewer_only_property_names(
    service: LoopbackService,
    name: str,
) -> None:
    response = service.client.get(CLAIM_PATH, headers=auth(NIKO_TOKEN))
    assert name not in response.text


@pytest.mark.parametrize("value", REVIEWER_ONLY_VALUES)
def test_employee_read_hides_reviewer_only_values(service: LoopbackService, value: str) -> None:
    response = service.client.get(CLAIM_PATH, headers=auth(NIKO_TOKEN))
    assert value not in response.text


def test_employee_read_returns_the_authorized_claim_data(service: LoopbackService) -> None:
    payload = service.client.get(CLAIM_PATH, headers=auth(NIKO_TOKEN)).json()
    assert payload["claim_id"] == CLAIM_FIXTURE.claim_id
    assert payload["employee_id"] == CLAIM_FIXTURE.employee_id
    assert payload["merchant"] == CLAIM_FIXTURE.merchant
    assert payload["amount_cents"] == CLAIM_FIXTURE.amount_cents
    assert payload["purpose"] == CLAIM_FIXTURE.purpose
    assert payload["status"] == CLAIM_FIXTURE.status
    assert payload["submitted_on"] == CLAIM_FIXTURE.submitted_on


def test_reviewer_read_includes_the_reviewer_only_properties(service: LoopbackService) -> None:
    """The employee projection is authorization, not deletion: the data still exists for `sol`."""
    response = service.client.get(CLAIM_PATH, headers=auth(SOL_TOKEN))
    assert response.status_code == 200
    payload = response.json()
    assert tuple(payload) == (*EMPLOYEE_VISIBLE_PROPERTIES, *REVIEWER_ONLY_PROPERTIES)
    assert payload["risk_score"] == CLAIM_FIXTURE.risk_score
    assert payload["reviewer_note"] == CLAIM_FIXTURE.reviewer_note
    assert payload["decision"] == CLAIM_FIXTURE.decision
    assert payload["approved_amount_cents"] == CLAIM_FIXTURE.approved_amount_cents


def test_reviewer_and_employee_agree_on_the_shared_properties(service: LoopbackService) -> None:
    employee = service.client.get(CLAIM_PATH, headers=auth(NIKO_TOKEN)).json()
    reviewer = service.client.get(CLAIM_PATH, headers=auth(SOL_TOKEN)).json()
    for name in EMPLOYEE_VISIBLE_PROPERTIES:
        assert employee[name] == reviewer[name]
