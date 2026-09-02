"""B-1: the owner key must never reach a place that persists it — query string or journal."""

from __future__ import annotations

import logging

import pytest
from fastapi.testclient import TestClient

from glasswell.api.access_log import ACCESS_LOGGER, REDACTED, install_access_log_redaction
from glasswell.api.errors import TYPE_BASE

OWNER_KEY = "f" * 64


def test_a_key_in_the_query_string_is_refused(client: TestClient) -> None:
    response = client.get("/v1/health", params={"key": OWNER_KEY})

    assert response.status_code == 422
    assert response.json()["type"] == f"{TYPE_BASE}/validation_failed"
    assert response.json()["errors"][0]["pointer"] == "/query/key"


def test_the_refusal_never_echoes_the_key_back(client: TestClient) -> None:
    response = client.get("/v1/health", params={"key": OWNER_KEY})

    assert OWNER_KEY not in response.text


def test_the_refusal_is_a_full_problem_document(client: TestClient) -> None:
    """The guard runs inside the request-id middleware, so the refusal joins the audit trail."""
    body = client.get("/v1/health", params={"key": OWNER_KEY}).json()

    assert body["request_id"]
    assert body["instance"] == "/v1/health"


def test_the_refusal_precedes_authentication(client: TestClient) -> None:
    """A wrong key in the query string is still a query-string key, not a 403 oracle."""
    anonymous = TestClient(client.app)

    assert anonymous.get("/v1/health", params={"key": "wrong"}).status_code == 422


def test_a_keyless_request_is_untouched(client: TestClient) -> None:
    assert client.get("/v1/health").status_code == 200


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


@pytest.mark.parametrize("parameter", ["key", "password", "token"])
def test_a_credential_in_the_query_string_is_refused(client, parameter: str) -> None:
    """A query string reaches the access log verbatim and the Referer of every outbound link."""
    response = client.get(f"/v1/health?{parameter}=whatever-they-typed")

    assert response.status_code == 422
    assert response.json()["errors"][0]["code"] == "credential_in_query"


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
