"""B-1: what the access log filter does to a line that carries a credential.

The route-level refusals -- a key in a query string is a 422 -- are asserted against the served
surface in tests/contract/test_key_hygiene.py. Nothing here needs one: the filter is a pure
function, and it was cloning a seeded contract database to read a log record.
"""

from __future__ import annotations

import logging

import pytest

from glasswell.api.access_log import ACCESS_LOGGER, REDACTED, install_access_log_redaction

OWNER_KEY = "f" * 64


def test_the_access_log_redacts_a_key_in_the_request_line(
    caplog: logging.LogRecord,
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
    from glasswell.api.access_log import redact

    line = 'GET /v1/wells cookie=__Host-gw_session=gws_QMDbEGaFjZUGhPEdmL2mFAPKJCCl6nqv'

    scrubbed = redact(line)
    bare = redact("gws_QMDbEGaFjZUGhPEdmL2mFAPKJCCl6nqv")

    assert "gws_QMDbEGaFjZUGhPEdmL2mFAPKJCCl6nqv" not in scrubbed
    assert scrubbed.endswith("__Host-gw_session=REDACTED")
    assert bare == "gws_REDACTED"


@pytest.mark.parametrize("name", ["key", "password", "token", "session", "csrf"])
def test_every_credential_shaped_query_parameter_is_redacted_from_a_log(name: str) -> None:
    from glasswell.api.access_log import redact

    scrubbed = redact(f"GET /v1/wells?{name}=the-secret-value HTTP/1.1")

    assert "the-secret-value" not in scrubbed
    assert f"{name}=REDACTED" in scrubbed
