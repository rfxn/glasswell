"""N-6: the response headers a same-origin app owes its browser, asserted on every surface.

SB-05 §1.5 owns the CSP content and SB-06 §4.5 owns where it is emitted. There is no Caddy
in the shipped path — uvicorn serves the SPA itself — so the origin emits them, and these
tests are what stops a later middleware reordering from dropping them.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from glasswell.api.examples import EXAMPLE_API10
from glasswell.api.security import (
    CSP_HEADER,
    CSP_REPORT_ONLY_HEADER,
    DOCS_PATH,
    REPORT_ONLY_ENV,
    SATELLITE_IMAGERY_ORIGIN,
    STATIC_SECURITY_HEADERS,
    content_security_policy,
    directives,
)

SURFACES = (
    "/healthz",
    "/v1",
    "/v1/health",
    f"/v1/wells/{EXAMPLE_API10}",
    "/v1/explain",
    "/v1/errors/not_found",
)


@pytest.mark.parametrize("path", SURFACES)
@pytest.mark.parametrize("header", sorted(STATIC_SECURITY_HEADERS))
def test_every_surface_carries_the_static_security_headers(
    client: TestClient, path: str, header: str
) -> None:
    response = client.get(path)

    assert response.headers[header] == STATIC_SECURITY_HEADERS[header]


@pytest.mark.parametrize("path", SURFACES)
def test_every_surface_carries_a_content_security_policy(client: TestClient, path: str) -> None:
    assert client.get(path).headers[CSP_HEADER]


def test_a_problem_response_is_still_a_document(client: TestClient) -> None:
    """A 403 renders in a browser tab like any other response, so it needs the same policy."""
    response = TestClient(client.app).get("/v1/health")

    assert response.status_code == 403
    assert response.headers[CSP_HEADER]
    assert response.headers["X-Content-Type-Options"] == "nosniff"


def test_the_policy_denies_framing_and_defaults_to_nothing(client: TestClient) -> None:
    policy = directives(client.get("/v1").headers[CSP_HEADER])

    assert policy["default-src"] == "'none'"
    assert policy["frame-ancestors"] == "'none'"
    assert policy["object-src"] == "'none'"
    assert policy["base-uri"] == "'none'"


def test_the_policy_admits_the_maplibre_worker_and_its_blob_url(client: TestClient) -> None:
    """The pinned maplibre build constructs its worker from a blob URL (SB-05 §1.5 note)."""
    policy = directives(client.get("/").headers[CSP_HEADER])

    assert policy["worker-src"] == "'self' blob:"
    assert "blob:" in policy["img-src"]


def test_the_policy_admits_same_origin_range_fetches_and_one_named_imagery_origin(
    client: TestClient,
) -> None:
    """PMTiles reads /basemap from this origin; imagery is the one external tile source."""
    policy = directives(client.get("/v1").headers[CSP_HEADER])

    assert policy["connect-src"] == f"'self' {SATELLITE_IMAGERY_ORIGIN}"
    assert SATELLITE_IMAGERY_ORIGIN in policy["img-src"]
    assert policy["script-src"] == "'self'"
    assert "unsafe-eval" not in client.get("/v1").headers[CSP_HEADER]


def test_the_imagery_origin_is_named_and_is_the_only_external_one_the_app_admits(
    client: TestClient,
) -> None:
    """A wildcard would admit every host the imagery vendor ever redirects to (DIR-1 ruling)."""
    policy = directives(client.get("/v1").headers[CSP_HEADER])
    external = {
        origin for value in policy.values() for origin in value.split() if origin.startswith("http")
    }

    assert external == {SATELLITE_IMAGERY_ORIGIN}
    assert SATELLITE_IMAGERY_ORIGIN.startswith("https://")
    assert "*" not in SATELLITE_IMAGERY_ORIGIN


def test_the_imagery_origin_is_absent_from_the_directives_that_load_code(
    client: TestClient,
) -> None:
    """Imagery is fetched and painted; it is never script, style, font or a frame."""
    policy = directives(client.get("/v1").headers[CSP_HEADER])

    for name in ("script-src", "style-src", "font-src", "worker-src", "child-src"):
        assert SATELLITE_IMAGERY_ORIGIN not in policy[name]


def test_the_plain_http_origin_does_not_upgrade_its_own_subresources() -> None:
    """The LAN break-glass path is served over http; upgrading would break every request."""
    assert "upgrade-insecure-requests" not in content_security_policy(https=False)
    assert "upgrade-insecure-requests" in content_security_policy(https=True)


def test_the_docs_page_names_its_vendored_origin_and_no_other_path_does(
    client: TestClient,
) -> None:
    """Swagger UI loads from a CDN; the exception is narrow, declared, and only on /docs."""
    docs = directives(client.get(DOCS_PATH).headers[CSP_HEADER])
    app_policy = client.get("/v1").headers[CSP_HEADER]

    assert "https://cdn.jsdelivr.net" in docs["script-src"]
    assert "cdn.jsdelivr.net" not in app_policy


def test_report_only_mode_swaps_the_header_and_never_emits_both(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """SB-05 §1.5's staged rollout: the enforcement lever is config, not a code edit."""
    monkeypatch.setenv(REPORT_ONLY_ENV, "1")

    response = client.get("/v1")

    assert response.headers[CSP_REPORT_ONLY_HEADER]
    assert CSP_HEADER not in response.headers
