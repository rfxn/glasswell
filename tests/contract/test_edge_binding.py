"""The static owner key is a deploy-gate credential, not an internet-reachable one.

`GLASSWELL_OWNER_KEY` has no expiry, no rotation path and no revocation row. Retaining it is
what keeps the deploy gate simple -- `deploy.sh` steps 8 and 9 run `verify.sh` and `smoke.sh`
on the host with no browser and no cookie jar -- but a bearer secret with that lifecycle
should not be usable from the internet. Issued `api_keys` rows carry an expiry and a
revocation row, so they stay valid on the tunnel and the non-interactive path survives.
"""

from __future__ import annotations

import pytest

from glasswell.api.examples import KEY_HEADER
from tests.conftest import CONTRACT_OWNER_KEY
from tests.contract.conftest import as_principal, issue_key

pytestmark = pytest.mark.contract

TUNNEL = {"X-Glasswell-Edge": "tunnel", "X-Glasswell-Client-Ip": "203.0.113.9"}
LAN = {"X-Glasswell-Edge": "lan", "X-Glasswell-Client-Ip": "192.168.2.50"}


def test_the_static_owner_key_is_refused_on_a_tunnel_marked_request(client) -> None:
    response = client.get("/v1/health", headers=TUNNEL)

    assert response.status_code == 403
    assert response.json()["type"] == "/v1/errors/unauthenticated"


def test_the_static_owner_key_is_accepted_with_no_edge_marker(client) -> None:
    """The unix socket path, which is how the deploy gate reaches the API."""
    assert client.get("/v1/health").status_code == 200


def test_the_static_owner_key_is_accepted_on_the_lan_listener(client) -> None:
    assert client.get("/v1/health", headers=LAN).status_code == 200


def test_an_issued_key_is_accepted_on_a_tunnel_marked_request(client) -> None:
    """Issued keys have an expiry and a revocation row, so the refusal does not apply."""
    secret = issue_key(client, label="edge-guest-2026", scope="guest")
    caller = as_principal(client, secret)

    assert caller.get("/v1/health", headers=TUNNEL).status_code == 200


def test_the_refusal_is_the_uniform_one_and_names_no_reason(client) -> None:
    body = client.get("/v1/health", headers=TUNNEL).json()

    assert "detail" not in body
    assert "tunnel" not in str(body).lower()


def test_a_client_cannot_reach_the_key_by_forging_the_edge_marker_away(client) -> None:
    """The forgery that matters runs the other way, and Caddy is what prevents it.

    A client cannot *remove* the marker Caddy sets, so this asserts the pairing the app
    relies on rather than a property the app could enforce alone: with no marker the request
    did not come through the tunnel, and `tests/unit/test_caddy_trust_headers.py` holds the
    listener contract that makes that true.
    """
    assert client.get("/v1/health", headers={"X-Glasswell-Edge": "lan"}).status_code == 200
    assert client.get("/v1/health", headers=TUNNEL).status_code == 403


def test_an_unrecognised_edge_marker_does_not_defeat_the_refusal(client) -> None:
    """A marker the app does not know is not a marker it trusts -- but it must not be a way
    to launder a tunnel request into an unmarked one either. `tunnel` is the only value that
    refuses, and anything else is treated as not-the-tunnel, which is why Caddy's delete of a
    client-supplied copy is the control rather than this check."""
    response = client.get("/v1/health", headers={"X-Glasswell-Edge": "elsewhere"})

    assert response.status_code == 200


def test_a_session_is_unaffected_by_the_edge_marker(client, owner_session) -> None:
    """The refusal is about one static bearer secret, not about the tunnel generally."""
    assert owner_session.get("/v1/health", headers=TUNNEL).status_code == 200


def test_the_owner_key_used_here_is_the_configured_one(client) -> None:
    """A floor: every assertion above is vacuous if the client is not actually sending it."""
    assert client.headers.get(KEY_HEADER) == CONTRACT_OWNER_KEY
