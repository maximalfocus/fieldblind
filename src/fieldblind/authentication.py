"""Demo-only credential resolution.

Identity is resolved server-side from a fixed bearer credential and from nothing else. No request
body, query parameter, or client-supplied role header participates.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from fieldblind.domain import DEMO_CREDENTIALS

if TYPE_CHECKING:
    from fieldblind.domain import Actor

_BEARER_PREFIX = "Bearer "


def resolve_actor(authorization_header: str | None) -> Actor | None:
    """Resolve the demonstration actor for a header value, or ``None`` for any failure.

    Missing, malformed, and unknown credentials are indistinguishable to the caller: they all map to
    ``None``, and the caller turns every one of them into the same generic response.
    """
    if authorization_header is None:
        return None
    if not authorization_header.startswith(_BEARER_PREFIX):
        return None
    credential = authorization_header.removeprefix(_BEARER_PREFIX).strip()
    if not credential:
        return None
    return DEMO_CREDENTIALS.get(credential)
