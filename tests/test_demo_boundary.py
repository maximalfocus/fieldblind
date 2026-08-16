"""The documented demonstration boundary: stable, labeled, and outside the contract."""

from __future__ import annotations

from typing import TYPE_CHECKING

from fieldblind.domain import CANONICAL_PROPERTY_ORDER, CLAIM_FIXTURE, DEMO_LABEL
from tests.support import (
    CLAIM_PATH,
    DEMO_STATE_PATH,
    NIKO_TOKEN,
    auth,
    canonical_claim,
    canonical_text,
)

if TYPE_CHECKING:
    from tests.conftest import LoopbackService


def test_canonical_state_uses_the_stable_property_order(service: LoopbackService) -> None:
    payload = service.client.get(DEMO_STATE_PATH).json()
    assert tuple(payload["claim"]) == CANONICAL_PROPERTY_ORDER


def test_canonical_state_is_labeled_as_a_fictional_local_demo(service: LoopbackService) -> None:
    assert service.client.get(DEMO_STATE_PATH).json()["label"] == DEMO_LABEL


def test_canonical_state_is_byte_for_byte_stable(service: LoopbackService) -> None:
    assert canonical_text(service.client) == canonical_text(service.client)


def test_canonical_state_starts_from_the_fixed_fixture(service: LoopbackService) -> None:
    claim = service.client.get(DEMO_STATE_PATH).json()["claim"]
    assert claim["claim_id"] == CLAIM_FIXTURE.claim_id
    assert claim["purpose"] == CLAIM_FIXTURE.purpose
    assert claim["decision"] == CLAIM_FIXTURE.decision
    assert claim["approved_amount_cents"] == CLAIM_FIXTURE.approved_amount_cents


def test_unknown_object_has_no_demonstration_state(service: LoopbackService) -> None:
    response = service.client.get("/demo/state/EXP-999")
    assert response.status_code == 404
    assert response.json()["error"] == "not_found"


def test_health_endpoint_reports_readiness(service: LoopbackService) -> None:
    response = service.client.get("/healthz")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_a_case_may_mutate_the_disposable_state(service: LoopbackService) -> None:
    """This case deliberately leaves state dirty; the next one proves it was reset."""
    response = service.client.patch(
        CLAIM_PATH,
        headers=auth(NIKO_TOKEN),
        json={"purpose": "left dirty by the previous case"},
    )
    assert response.status_code == 200
    assert canonical_claim(service.client)["purpose"] == "left dirty by the previous case"


def test_the_next_case_starts_from_the_fixed_fixture(service: LoopbackService) -> None:
    assert canonical_claim(service.client)["purpose"] == CLAIM_FIXTURE.purpose
