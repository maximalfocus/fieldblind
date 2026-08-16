"""The shared object-level boundary answers before any property is considered."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from fieldblind.domain import CANONICAL_PROPERTY_ORDER, REVIEWER_ONLY_PROPERTIES
from tests.support import (
    CLAIM_PATH,
    SOL_TOKEN,
    UMA_TOKEN,
    UNKNOWN_CLAIM_PATH,
    auth,
    canonical_text,
)

if TYPE_CHECKING:
    from tests.conftest import LoopbackService


@pytest.mark.parametrize("path", [CLAIM_PATH, UNKNOWN_CLAIM_PATH])
def test_non_owner_read_is_not_found(service: LoopbackService, path: str) -> None:
    response = service.client.get(path, headers=auth(UMA_TOKEN))
    assert response.status_code == 404
    assert response.json()["error"] == "not_found"


def test_non_owner_and_unknown_object_are_indistinguishable(service: LoopbackService) -> None:
    owned = service.client.get(CLAIM_PATH, headers=auth(UMA_TOKEN))
    unknown = service.client.get(UNKNOWN_CLAIM_PATH, headers=auth(UMA_TOKEN))
    assert owned.status_code == unknown.status_code
    assert set(owned.json()) == set(unknown.json())
    assert owned.json()["error"] == unknown.json()["error"]


def test_non_owner_update_is_not_found_and_changes_nothing(service: LoopbackService) -> None:
    before = canonical_text(service.client)
    response = service.client.patch(
        CLAIM_PATH,
        headers=auth(UMA_TOKEN),
        json={"purpose": "seized", "decision": "approved", "approved_amount_cents": 8640},
    )
    assert response.status_code == 404
    assert canonical_text(service.client) == before


def test_object_refusal_discloses_no_property(service: LoopbackService) -> None:
    body = service.client.get(CLAIM_PATH, headers=auth(UMA_TOKEN)).text
    for name in CANONICAL_PROPERTY_ORDER:
        assert name not in body


def test_object_refusal_emits_no_audit_event(service: LoopbackService) -> None:
    """A caller who fails the object check triggers no property-level decision at all."""
    service.client.patch(CLAIM_PATH, headers=auth(UMA_TOKEN), json={"decision": "approved"})
    assert service.logs.events("property_update_rejected") == []


def test_reviewer_may_access_the_claim(service: LoopbackService) -> None:
    response = service.client.get(CLAIM_PATH, headers=auth(SOL_TOKEN))
    assert response.status_code == 200
    for name in REVIEWER_ONLY_PROPERTIES:
        assert name in response.json()
