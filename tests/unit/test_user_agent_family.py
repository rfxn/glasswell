"""The coarse client label the session list renders.

Computed at login, never at read time: `sessions.user_agent_sha256` is one-way, so SQL cannot
recover a family from it. The label is decoration on a list — it is never an authorization
input, and an unrecognised string resolves to the same `unknown` an absent header does.
"""

from __future__ import annotations

import pytest

from glasswell.api.accounts import UNKNOWN_USER_AGENT, user_agent_family

CHROME_MAC = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko)"
    " Chrome/140.0.0.0 Safari/537.36"
)
EDGE_WINDOWS = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko)"
    " Chrome/140.0.0.0 Safari/537.36 Edg/140.0.0.0"
)
FIREFOX_LINUX = "Mozilla/5.0 (X11; Linux x86_64; rv:131.0) Gecko/20100101 Firefox/131.0"
SAFARI_IOS = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like"
    " Gecko) Version/17.6 Mobile/15E148 Safari/604.1"
)
CHROME_ANDROID = (
    "Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 (KHTML, like Gecko)"
    " Chrome/140.0.0.0 Mobile Safari/537.36"
)


@pytest.mark.parametrize(
    ("user_agent", "expected"),
    [
        (CHROME_MAC, "Chrome on macOS"),
        # Edge and Chrome both claim Safari, and Edge also claims Chrome, so the order the
        # tokens are tested in is the whole of the correctness here.
        (EDGE_WINDOWS, "Edge on Windows"),
        (FIREFOX_LINUX, "Firefox on Linux"),
        (SAFARI_IOS, "Safari on iOS"),
        (CHROME_ANDROID, "Chrome on Android"),
    ],
)
def test_a_known_pair_reads_as_browser_on_system(user_agent: str, expected: str) -> None:
    assert user_agent_family(user_agent) == expected


@pytest.mark.parametrize(
    "user_agent",
    [
        None,
        "",
        "   ",
        "curl/8.9.1",
        "glasswell-deploy-gate/1.0",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
        "Firefox/131.0",
        "<script>alert(1)</script>",
    ],
)
def test_anything_unrecognised_is_unknown(user_agent: str | None) -> None:
    """Half a pair is not a pair. A machine caller, an absent header and a hostile string all
    resolve to the same value, so the column cannot be read as a claim about the client."""
    assert user_agent_family(user_agent) == UNKNOWN_USER_AGENT


def test_the_label_never_carries_the_raw_header() -> None:
    """A family is a label, not a copy: an unbounded header echoed into a list is a payload."""
    hostile = f"{CHROME_MAC} secret-token-abcdefghijklmnop"

    family = user_agent_family(hostile)

    assert family == "Chrome on macOS"
    assert "secret-token" not in family
