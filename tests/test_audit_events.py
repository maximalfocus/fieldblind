"""Audit-event cardinality, bounded fields, and redaction."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest

from fieldblind.domain import CLAIM_FIXTURE, DEMO_CREDENTIALS, REVIEWER_ONLY_PROPERTIES
from fieldblind.observability import AUDIT_HISTORY_LIMIT, EVENT_FIELDS, REASON_CODES
from tests.support import CLAIM_PATH, NIKO_TOKEN, SOL_TOKEN, auth

if TYPE_CHECKING:
    from tests.conftest import LoopbackService

REJECTED = "property_update_rejected"

MIXED_BODY: dict[str, Any] = {
    "purpose": "revised",
    "decision": "approved",
    "approved_amount_cents": 8640,
}


def test_mixed_body_emits_exactly_one_audit_event(service: LoopbackService) -> None:
    service.client.patch(CLAIM_PATH, headers=auth(NIKO_TOKEN), json=MIXED_BODY)
    assert len(service.logs.events(REJECTED)) == 1


def test_audit_event_carries_the_required_bounded_fields(service: LoopbackService) -> None:
    service.client.patch(CLAIM_PATH, headers=auth(NIKO_TOKEN), json=MIXED_BODY)
    (event,) = service.logs.events(REJECTED)
    assert set(event) == {"event", "request_id", "actor_id", "object_id", "outcome", "reason_code"}
    assert set(event) <= EVENT_FIELDS
    assert event["actor_id"] == "niko"
    assert event["object_id"] == CLAIM_FIXTURE.claim_id
    assert event["outcome"] == "rejected"
    assert event["reason_code"] in REASON_CODES
    assert event["request_id"]


def test_audit_event_correlates_with_the_client_response(service: LoopbackService) -> None:
    response = service.client.patch(CLAIM_PATH, headers=auth(NIKO_TOKEN), json=MIXED_BODY)
    (event,) = service.logs.events(REJECTED)
    assert event["request_id"] == response.json()["request_id"]


@pytest.mark.parametrize("name", REVIEWER_ONLY_PROPERTIES)
def test_audit_event_names_no_protected_property(service: LoopbackService, name: str) -> None:
    service.client.patch(CLAIM_PATH, headers=auth(NIKO_TOKEN), json=MIXED_BODY)
    assert name not in service.logs.payload_text()


def test_logs_contain_no_body_credential_or_protected_value(service: LoopbackService) -> None:
    service.client.patch(CLAIM_PATH, headers=auth(NIKO_TOKEN), json=MIXED_BODY)
    service.client.get(CLAIM_PATH, headers=auth(SOL_TOKEN))
    service.client.patch(CLAIM_PATH, headers=auth(SOL_TOKEN), json={"decision": "approved"})
    emitted = service.logs.payload_text()
    for credential in DEMO_CREDENTIALS:
        assert credential not in emitted
    assert CLAIM_FIXTURE.reviewer_note not in emitted
    assert str(CLAIM_FIXTURE.risk_score) not in emitted
    assert "revised" not in emitted
    assert "purpose" not in emitted


def test_accepted_update_emits_no_rejection_event(service: LoopbackService) -> None:
    service.client.patch(CLAIM_PATH, headers=auth(NIKO_TOKEN), json={"purpose": "revised"})
    assert service.logs.events(REJECTED) == []


def test_unauthenticated_update_emits_no_property_event(service: LoopbackService) -> None:
    service.client.patch(CLAIM_PATH, json=MIXED_BODY)
    assert service.logs.events(REJECTED) == []


def test_every_request_is_access_logged_without_content(service: LoopbackService) -> None:
    service.client.get(CLAIM_PATH, headers=auth(NIKO_TOKEN))
    completed = service.logs.events("request_completed")
    assert completed
    assert set(completed[-1]) == {"event", "request_id", "method", "status"}
    assert completed[-1]["method"] == "GET"
    assert completed[-1]["status"] == 200


def test_the_demonstration_event_view_matches_the_emitted_event(
    service: LoopbackService,
) -> None:
    service.client.post("/demo/reset")
    service.client.patch(CLAIM_PATH, headers=auth(NIKO_TOKEN), json=MIXED_BODY)
    exposed = service.client.get("/demo/events").json()["events"]
    assert len(exposed) == 1
    assert exposed[0] == service.logs.events(REJECTED)[-1]


def test_the_audit_history_stays_bounded(service: LoopbackService) -> None:
    """Bounded on purpose: this is a fixed teaching fixture, not an audit store."""
    service.client.post("/demo/reset")
    for _ in range(AUDIT_HISTORY_LIMIT + 5):
        service.client.patch(CLAIM_PATH, headers=auth(NIKO_TOKEN), json=MIXED_BODY)
    exposed = service.client.get("/demo/events").json()["events"]
    assert len(exposed) == AUDIT_HISTORY_LIMIT


def test_the_demonstration_event_view_leaks_nothing(service: LoopbackService) -> None:
    service.client.patch(CLAIM_PATH, headers=auth(NIKO_TOKEN), json=MIXED_BODY)
    body = service.client.get("/demo/events").text
    for name in REVIEWER_ONLY_PROPERTIES:
        assert name not in body
    assert "purpose" not in body
    for credential in DEMO_CREDENTIALS:
        assert credential not in body
