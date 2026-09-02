"""What the access-log filter redacts, and what it must leave alone.

uvicorn logs the request line verbatim, so a credential in a query string lands in journald in
cleartext. The API refuses four credential-shaped parameters outright; this filter is the
second line. The pattern matches *inside* an identifier, because `\\b` before a bare `password`
never fires on `new_password=` — `_` is a word character.

The two directions are tested together on purpose. Over-redaction (`monkey=`) is the safe
direction and is accepted; under-redaction of a live query string is not, because a log that
redacts `limit=20` stops being a record of what was asked.
"""

from __future__ import annotations

import pytest

from glasswell.api.access_log import redact

REDACTED_CASES = (
    ("?new_password=hunter2", "new_password=REDACTED", "hunter2"),
    ("?owner_key=abc", "owner_key=REDACTED", "abc"),
    ("?x_csrf_token=abc", "x_csrf_token=REDACTED", "abc"),
    ("?password=hunter2", "password=REDACTED", "hunter2"),
    ("?csrf=abc", "csrf=REDACTED", "abc"),
    # Acknowledged over-redaction: `monkey` ends in `key`. A redacted log value is recoverable
    # from the request; a leaked credential is not.
    ("?monkey=1", "monkey=REDACTED", None),
)

# Every query string this API actually serves, taken off the documented examples. None of them
# may be touched: a filter that eats the request's parameters has eaten the access log.
UNTOUCHED_CASES = (
    "?limit=20&as_of=2026-08-01&explain=true",
    "?h=drv_obqajdni25f25zmxcz7a&format=dot",
    "?bbox=-104,47.5,-103,48.5&explain=true",
    "?state=33&by=operator&top=15",
    # No match: `csrfy` is not `csrf` followed by `=`.
    "?csrfy=abc",
)


@pytest.mark.parametrize(
    ("line", "expected", "secret"), REDACTED_CASES, ids=[case[0] for case in REDACTED_CASES]
)
def test_a_credential_shaped_parameter_is_redacted(
    line: str, expected: str, secret: str | None
) -> None:
    scrubbed = redact(f"GET /v1/wells{line} HTTP/1.1")

    assert expected in scrubbed
    if secret is not None:
        assert secret not in scrubbed


@pytest.mark.parametrize("line", UNTOUCHED_CASES)
def test_a_live_query_string_passes_through_unchanged(line: str) -> None:
    record = f'127.0.0.1 - "GET /v1/wells{line} HTTP/1.1" 200'

    assert redact(record) == record


def test_the_eight_served_parameter_names_are_never_redacted() -> None:
    """Named one by one, so a future widening of the pattern fails here rather than in the log."""
    served = ("limit", "as_of", "explain", "format", "bbox", "state", "by", "top")

    for name in served:
        assert redact(f"?{name}=value") == f"?{name}=value"


def test_a_session_token_is_redacted_wherever_it_appears() -> None:
    """The query pattern reaches a cookie header too, and the token pattern covers a bare one."""
    token = "gws_QMDbEGaFjZUGhPEdmL2mFAPKJCCl6nqv"

    in_a_cookie = redact(f"GET /v1/wells cookie=__Host-gw_session={token}")
    on_its_own = redact(f"a stray repr of a token: {token}")

    assert token not in in_a_cookie
    assert "__Host-gw_session=REDACTED" in in_a_cookie
    assert on_its_own.endswith("gws_REDACTED")
