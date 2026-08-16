"""Every accepted update is one transaction, and every failure rolls back completely."""

from __future__ import annotations

from typing import TYPE_CHECKING

from fieldblind.service import set_pre_commit_hook
from tests.support import CLAIM_PATH, NIKO_TOKEN, SOL_TOKEN, auth, canonical_text

if TYPE_CHECKING:
    from tests.conftest import LoopbackService


class InjectedFailureError(RuntimeError):
    """A deliberate pre-commit failure with no message worth leaking."""


def _fail_before_commit() -> None:
    raise InjectedFailureError


def test_pre_commit_failure_rolls_back_the_employee_update(service: LoopbackService) -> None:
    before = canonical_text(service.client)
    set_pre_commit_hook(_fail_before_commit)
    response = service.client.patch(
        CLAIM_PATH,
        headers=auth(NIKO_TOKEN),
        json={"purpose": "never committed"},
    )
    assert response.status_code == 500
    set_pre_commit_hook(None)
    assert canonical_text(service.client) == before


def test_pre_commit_failure_rolls_back_the_reviewer_update(service: LoopbackService) -> None:
    before = canonical_text(service.client)
    set_pre_commit_hook(_fail_before_commit)
    response = service.client.patch(
        CLAIM_PATH,
        headers=auth(SOL_TOKEN),
        json={"decision": "approved", "approved_amount_cents": 8640},
    )
    assert response.status_code == 500
    set_pre_commit_hook(None)
    assert canonical_text(service.client) == before


def test_pre_commit_failure_returns_a_generic_response(service: LoopbackService) -> None:
    set_pre_commit_hook(_fail_before_commit)
    response = service.client.patch(
        CLAIM_PATH,
        headers=auth(NIKO_TOKEN),
        json={"purpose": "never committed"},
    )
    set_pre_commit_hook(None)
    assert set(response.json()) == {"error", "request_id"}
    assert response.json()["error"] == "internal_error"
    assert "never committed" not in response.text


def test_the_service_still_works_after_a_rolled_back_update(service: LoopbackService) -> None:
    set_pre_commit_hook(_fail_before_commit)
    service.client.patch(CLAIM_PATH, headers=auth(NIKO_TOKEN), json={"purpose": "never committed"})
    set_pre_commit_hook(None)
    response = service.client.patch(
        CLAIM_PATH,
        headers=auth(NIKO_TOKEN),
        json={"purpose": "committed"},
    )
    assert response.status_code == 200
    assert '"purpose":"committed"' in canonical_text(service.client)
