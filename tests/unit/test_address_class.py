"""What `address_class` says, and what it deliberately does not say.

The session list serves a class rather than the address a session was created from: no SB-04
§3 or SB-06 §5 ruling permits a client address in a body, and `routers/` has no audit route
that serves one. The derivation is `ipaddress.is_private`, which answers *not globally
routable* rather than *on this network* — a distinction that only shows up in fixtures, where
the RFC 5737 documentation ranges read as `lan`.
"""

from __future__ import annotations

import pytest

from glasswell.api.accounts import UNKNOWN_IP
from glasswell.api.routers.sessions import LAN, REMOTE, UNKNOWN, _address_class


@pytest.mark.parametrize(
    ("address", "expected"),
    [
        ("192.168.2.41", LAN),
        ("10.0.0.1", LAN),
        ("127.0.0.1", LAN),
        ("fd00::1", LAN),
        ("8.8.8.8", REMOTE),
        ("2001:4860:4860::8888", REMOTE),
        # RFC 5737 / RFC 3849 documentation space is private to python, and every contract
        # fixture uses it. Recorded rather than worked around: the class is a hint on a list.
        ("198.51.100.4", LAN),
        ("203.0.113.9", LAN),
    ],
)
def test_an_address_resolves_to_a_class(address: str, expected: str) -> None:
    assert _address_class(address) == expected


@pytest.mark.parametrize("value", [None, "", UNKNOWN_IP, "not-an-address", "10.0.0.999"])
def test_anything_unresolvable_is_unknown(value: str | None) -> None:
    """`resolve_client_ip` answers UNKNOWN whenever the request carried no edge marker, which
    is most of them, so `unknown` is the honest majority rather than an error case."""
    assert _address_class(value) == UNKNOWN
