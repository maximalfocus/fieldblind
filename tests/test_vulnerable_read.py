"""The read-side flaw: generic serialization hands an employee every reviewer-only property."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from fieldblind.domain import (
    CANONICAL_PROPERTY_ORDER,
    CLAIM_FIXTURE,
    EMPLOYEE_VISIBLE_PROPERTIES,
    REVIEWER_ONLY_PROPERTIES,
)
from tests.support import CLAIM_PATH, NIKO_TOKEN, SOL_TOKEN, auth

if TYPE_CHECKING:
    from tests.conftest import LoopbackService


def test_vulnerable_employee_read_exposes_exactly_the_reviewer_only_properties(
    vulnerable_service: LoopbackService,
) -> None:
    """Exactly four properties leak: no fewer, and nothing else the model happens to hold."""
    response = vulnerable_service.client.get(CLAIM_PATH, headers=auth(NIKO_TOKEN))
    assert response.status_code == 200
    exposed = set(response.json())
    assert exposed - set(EMPLOYEE_VISIBLE_PROPERTIES) == set(REVIEWER_ONLY_PROPERTIES)
    assert exposed == set(CANONICAL_PROPERTY_ORDER)


@pytest.mark.parametrize("name", REVIEWER_ONLY_PROPERTIES)
def test_vulnerable_employee_read_leaks_the_fixed_values(
    vulnerable_service: LoopbackService,
    name: str,
) -> None:
    payload = vulnerable_service.client.get(CLAIM_PATH, headers=auth(NIKO_TOKEN)).json()
    assert payload[name] == getattr(CLAIM_FIXTURE, name)


def test_the_leak_is_the_serializer_and_not_the_object_policy(
    service: LoopbackService,
    vulnerable_service: LoopbackService,
) -> None:
    """Both variants agree the employee may read the claim; only one respects its properties."""
    secure = service.client.get(CLAIM_PATH, headers=auth(NIKO_TOKEN))
    vulnerable = vulnerable_service.client.get(CLAIM_PATH, headers=auth(NIKO_TOKEN))
    assert secure.status_code == vulnerable.status_code == 200
    assert set(secure.json()) == set(EMPLOYEE_VISIBLE_PROPERTIES)
    assert set(vulnerable.json()) == set(CANONICAL_PROPERTY_ORDER)
    for name in EMPLOYEE_VISIBLE_PROPERTIES:
        assert secure.json()[name] == vulnerable.json()[name]


def test_the_reviewer_sees_the_same_data_in_both_variants(
    service: LoopbackService,
    vulnerable_service: LoopbackService,
) -> None:
    """The reviewer was always allowed these properties, so the flaw changes nothing for them."""
    secure = service.client.get(CLAIM_PATH, headers=auth(SOL_TOKEN)).json()
    vulnerable = vulnerable_service.client.get(CLAIM_PATH, headers=auth(SOL_TOKEN)).json()
    assert secure == vulnerable


def test_vulnerable_read_reaches_only_its_own_fixed_object(
    vulnerable_service: LoopbackService,
) -> None:
    """There is no enumerator here: an unknown identifier is simply not found."""
    response = vulnerable_service.client.get("/claims/EXP-999", headers=auth(NIKO_TOKEN))
    assert response.status_code == 404
    assert response.json()["error"] == "not_found"
