"""Credentials are resolved server-side, and every credential failure looks identical."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from fieldblind.authentication import resolve_actor
from fieldblind.domain import REVIEWER_ONLY_PROPERTIES
from tests.support import CLAIM_PATH, NIKO_TOKEN, auth, canonical_text

if TYPE_CHECKING:
    from tests.conftest import LoopbackService

BAD_HEADERS = [
    pytest.param(None, id="missing"),
    pytest.param({"Authorization": ""}, id="empty"),
    pytest.param({"Authorization": "Bearer"}, id="prefix-only"),
    pytest.param({"Authorization": NIKO_TOKEN}, id="no-bearer-scheme"),
    pytest.param({"Authorization": "Basic bmlrbzpuaWtv"}, id="wrong-scheme"),
    pytest.param({"Authorization": "Bearer fictional-demo-token-unknown"}, id="unknown"),
    pytest.param({"Authorization": "Bearer fictional-demo-token-NIKO"}, id="wrong-case"),
]

# An HTTP client refuses to transmit a header value with trailing whitespace, so the
# blank-credential case is proved at the resolver instead of over the wire.
BLANK_CREDENTIAL_HEADERS = ["Bearer ", "Bearer    ", "Bearer \t"]


@pytest.mark.parametrize("headers", BAD_HEADERS)
def test_read_without_a_valid_credential_is_uniformly_unauthorized(
    service: LoopbackService,
    headers: dict[str, str] | None,
) -> None:
    response = service.client.get(CLAIM_PATH, headers=headers)
    assert response.status_code == 401
    assert set(response.json()) == {"error", "request_id"}
    assert response.json()["error"] == "unauthorized"


@pytest.mark.parametrize("headers", BAD_HEADERS)
def test_update_without_a_valid_credential_is_uniformly_unauthorized(
    service: LoopbackService,
    headers: dict[str, str] | None,
) -> None:
    before = canonical_text(service.client)
    response = service.client.patch(CLAIM_PATH, headers=headers, json={"purpose": "changed"})
    assert response.status_code == 401
    assert response.json()["error"] == "unauthorized"
    assert canonical_text(service.client) == before


@pytest.mark.parametrize("header", BLANK_CREDENTIAL_HEADERS)
def test_blank_credential_resolves_to_no_actor(header: str) -> None:
    assert resolve_actor(header) is None


def test_unauthorized_response_leaks_no_property(service: LoopbackService) -> None:
    body = service.client.get(CLAIM_PATH).text
    for name in REVIEWER_ONLY_PROPERTIES:
        assert name not in body


def test_role_is_never_taken_from_the_request(service: LoopbackService) -> None:
    """A client cannot promote itself to reviewer through content it controls."""
    response = service.client.get(
        CLAIM_PATH,
        headers={**auth(NIKO_TOKEN), "X-Role": "reviewer", "X-Actor-Id": "sol"},
        params={"actor": "sol", "role": "reviewer"},
    )
    assert response.status_code == 200
    for name in REVIEWER_ONLY_PROPERTIES:
        assert name not in response.text


def test_body_supplied_role_cannot_select_the_reviewer_contract(service: LoopbackService) -> None:
    before = canonical_text(service.client)
    response = service.client.patch(
        CLAIM_PATH,
        headers=auth(NIKO_TOKEN),
        json={"role": "reviewer", "decision": "approved"},
    )
    assert response.status_code == 400
    assert canonical_text(service.client) == before


def test_credentials_never_reach_the_logs(service: LoopbackService) -> None:
    service.client.get(CLAIM_PATH, headers=auth(NIKO_TOKEN))
    service.client.get(CLAIM_PATH, headers={"Authorization": "Bearer fictional-demo-token-unknown"})
    joined = "\n".join(service.logs.lines)
    assert "fictional-demo-token" not in joined
    assert "Bearer" not in joined
