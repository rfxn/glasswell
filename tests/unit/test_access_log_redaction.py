"""B-1: what the access-log filter redacts, and what it must leave alone.

uvicorn logs the request line verbatim, so a credential in a query string lands in journald in
cleartext. The API refuses four credential-shaped parameters outright; this filter is the
second line. The pattern matches *inside* an identifier, because `\\b` before a bare `password`
never fires on `new_password=` — `_` is a word character.

The two directions are tested together on purpose. Over-redaction (`monkey=`) is the safe
direction and is accepted; under-redaction of a live query string is not, because a log that
redacts `limit=20` stops being a record of what was asked.

The route-level refusals — a key in a query string is a 422 — are asserted against the served
surface in tests/contract/test_key_hygiene.py. Nothing here needs one: `redact` is a pure
function, and the three tests at the foot reach it through the logging filter and
`install_access_log_redaction()` rather than through a database.
"""

from __future__ import annotations

import logging

import pytest

from glasswell.api.access_log import (
    ACCESS_LOGGER,
    REDACTED,
    install_access_log_redaction,
    redact,
)

OWNER_KEY = "f" * 64

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


def test_the_access_log_redacts_a_key_in_the_request_line(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """uvicorn logs the request line verbatim; the filter is what keeps it out of journald."""
    install_access_log_redaction()
    logger = logging.getLogger(ACCESS_LOGGER)

    with caplog.at_level(logging.INFO, logger=ACCESS_LOGGER):
        logger.info('%s - "%s %s HTTP/%s" %d', "10.0.0.1", "GET", f"/?key={OWNER_KEY}", "1.1", 200)

    assert OWNER_KEY not in caplog.text
    assert REDACTED in caplog.text


def test_a_session_token_in_a_log_record_is_redacted() -> None:
    """Two rules reach a token, and which one fires depends on what precedes it. In a cookie
    header the credential-parameter pattern takes the whole assignment; standing on its own the
    token pattern takes the token. Neither survives, which is the property that matters."""
    line = "GET /v1/wells cookie=__Host-gw_session=gws_QMDbEGaFjZUGhPEdmL2mFAPKJCCl6nqv"

    scrubbed = redact(line)
    bare = redact("gws_QMDbEGaFjZUGhPEdmL2mFAPKJCCl6nqv")

    assert "gws_QMDbEGaFjZUGhPEdmL2mFAPKJCCl6nqv" not in scrubbed
    assert scrubbed.endswith("__Host-gw_session=REDACTED")
    assert bare == "gws_REDACTED"


@pytest.mark.parametrize("name", ["key", "password", "token", "session", "csrf"])
def test_every_credential_shaped_query_parameter_is_redacted_from_a_log(name: str) -> None:
    scrubbed = redact(f"GET /v1/wells?{name}=the-secret-value HTTP/1.1")

    assert "the-secret-value" not in scrubbed
    assert f"{name}=REDACTED" in scrubbed
