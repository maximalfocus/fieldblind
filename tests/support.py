"""Small helpers shared by the demonstration test suite."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Final

from fieldblind.domain import CLAIM_FIXTURE, DEMO_CREDENTIALS, NIKO, SOL, UMA

if TYPE_CHECKING:
    import httpx

CLAIM_PATH: Final = f"/claims/{CLAIM_FIXTURE.claim_id}"
DEMO_STATE_PATH: Final = f"/demo/state/{CLAIM_FIXTURE.claim_id}"
DEMO_RESET_PATH: Final = "/demo/reset"
UNKNOWN_CLAIM_PATH: Final = "/claims/EXP-999"

TOKENS: Final[dict[str, str]] = {
    actor.actor_id: credential for credential, actor in DEMO_CREDENTIALS.items()
}

NIKO_TOKEN: Final = TOKENS[NIKO.actor_id]
UMA_TOKEN: Final = TOKENS[UMA.actor_id]
SOL_TOKEN: Final = TOKENS[SOL.actor_id]


def auth(token: str) -> dict[str, str]:
    """Build the bearer header for a fixed demo credential."""
    return {"Authorization": f"Bearer {token}"}


def canonical_text(client: httpx.Client) -> str:
    """Return the canonical state exactly as the demonstration boundary serialized it."""
    response = client.get(DEMO_STATE_PATH)
    assert response.status_code == 200, response.text
    return response.text


def canonical_claim(client: httpx.Client) -> dict[str, Any]:
    """Return the canonical claim state as a mapping."""
    response = client.get(DEMO_STATE_PATH)
    assert response.status_code == 200, response.text
    claim: dict[str, Any] = response.json()["claim"]
    return claim
