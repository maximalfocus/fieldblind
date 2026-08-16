"""The two variants differ at the property boundary and nowhere else, and cannot contaminate each
other.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest

from fieldblind.domain import CANONICAL_PROPERTY_ORDER, CLAIM_FIXTURE
from tests.support import (
    CLAIM_PATH,
    DEMO_RESET_PATH,
    NIKO_TOKEN,
    UMA_TOKEN,
    UNKNOWN_CLAIM_PATH,
    auth,
    canonical_claim,
    canonical_text,
)

if TYPE_CHECKING:
    from tests.conftest import LoopbackService

BAD_HEADERS = [
    pytest.param(None, id="missing"),
    pytest.param({"Authorization": ""}, id="empty"),
    pytest.param({"Authorization": "Bearer"}, id="prefix-only"),
    pytest.param({"Authorization": "Basic bmlrbzpuaWtv"}, id="wrong-scheme"),
    pytest.param({"Authorization": "Bearer fictional-demo-token-unknown"}, id="unknown"),
]

MIXED_BODY: dict[str, Any] = {
    "purpose": "revised",
    "decision": "approved",
    "approved_amount_cents": 8640,
}


@pytest.mark.parametrize("headers", BAD_HEADERS)
def test_authentication_is_identical_in_both_variants(
    service: LoopbackService,
    vulnerable_service: LoopbackService,
    headers: dict[str, str] | None,
) -> None:
    secure = service.client.get(CLAIM_PATH, headers=headers)
    vulnerable = vulnerable_service.client.get(CLAIM_PATH, headers=headers)
    assert secure.status_code == vulnerable.status_code == 401
    assert secure.json()["error"] == vulnerable.json()["error"] == "unauthorized"


@pytest.mark.parametrize("path", [CLAIM_PATH, UNKNOWN_CLAIM_PATH])
def test_the_object_boundary_is_identical_in_both_variants(
    service: LoopbackService,
    vulnerable_service: LoopbackService,
    path: str,
) -> None:
    secure = service.client.get(path, headers=auth(UMA_TOKEN))
    vulnerable = vulnerable_service.client.get(path, headers=auth(UMA_TOKEN))
    assert secure.status_code == vulnerable.status_code == 404
    assert secure.json()["error"] == vulnerable.json()["error"] == "not_found"


def test_the_non_owner_cannot_exploit_the_vulnerable_variant(
    vulnerable_service: LoopbackService,
) -> None:
    """The deliberate flaw is BOPLA, not BOLA: the object check still stops a non-owner."""
    before = canonical_text(vulnerable_service.client)
    response = vulnerable_service.client.patch(
        CLAIM_PATH,
        headers=auth(UMA_TOKEN),
        json=MIXED_BODY,
    )
    assert response.status_code == 404
    for name in CANONICAL_PROPERTY_ORDER:
        assert name not in response.text
    assert canonical_text(vulnerable_service.client) == before


def test_an_unauthenticated_caller_cannot_exploit_the_vulnerable_variant(
    vulnerable_service: LoopbackService,
) -> None:
    before = canonical_text(vulnerable_service.client)
    response = vulnerable_service.client.patch(CLAIM_PATH, json=MIXED_BODY)
    assert response.status_code == 401
    assert canonical_text(vulnerable_service.client) == before


def test_both_variants_start_from_the_identical_canonical_fixture(
    service: LoopbackService,
    vulnerable_service: LoopbackService,
) -> None:
    assert canonical_text(service.client) == canonical_text(vulnerable_service.client)


def test_mutating_the_vulnerable_variant_leaves_the_secure_one_untouched(
    service: LoopbackService,
    vulnerable_service: LoopbackService,
) -> None:
    """Separate disposable databases: an attack case cannot contaminate the secure result."""
    before_secure = canonical_text(service.client)
    vulnerable_service.client.patch(CLAIM_PATH, headers=auth(NIKO_TOKEN), json=MIXED_BODY)
    assert canonical_claim(vulnerable_service.client)["decision"] == "approved"
    assert canonical_text(service.client) == before_secure


def test_mutating_the_secure_variant_leaves_the_vulnerable_one_untouched(
    service: LoopbackService,
    vulnerable_service: LoopbackService,
) -> None:
    before_vulnerable = canonical_text(vulnerable_service.client)
    service.client.patch(CLAIM_PATH, headers=auth(NIKO_TOKEN), json={"purpose": "secure edit"})
    assert canonical_claim(service.client)["purpose"] == "secure edit"
    assert canonical_text(vulnerable_service.client) == before_vulnerable


@pytest.mark.parametrize("variant", ["secure", "vulnerable"])
def test_each_variant_resets_to_the_canonical_fixture(
    service: LoopbackService,
    vulnerable_service: LoopbackService,
    variant: str,
) -> None:
    target = service if variant == "secure" else vulnerable_service
    baseline = canonical_text(target.client)
    target.client.patch(CLAIM_PATH, headers=auth(NIKO_TOKEN), json={"purpose": "dirty"})
    assert canonical_claim(target.client)["purpose"] == "dirty"

    reset = target.client.post(DEMO_RESET_PATH)
    assert reset.status_code == 200
    assert canonical_text(target.client) == baseline
    assert canonical_claim(target.client)["purpose"] == CLAIM_FIXTURE.purpose


def test_resetting_one_variant_does_not_reset_the_other(
    service: LoopbackService,
    vulnerable_service: LoopbackService,
) -> None:
    service.client.patch(CLAIM_PATH, headers=auth(NIKO_TOKEN), json={"purpose": "secure edit"})
    vulnerable_service.client.post(DEMO_RESET_PATH)
    assert canonical_claim(service.client)["purpose"] == "secure edit"
