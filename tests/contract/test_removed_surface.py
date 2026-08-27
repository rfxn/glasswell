"""Removal proofs for the pre-v1 freeze: S-A's envelope mirror and S-K's `ref` alias.

Both removals had to happen in this window. §3.6.1 makes a field or parameter removal a
`/v2` event once the OpenAPI document is published for S1, so these tests exist to make a
reinstatement fail rather than to describe what was deleted.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from glasswell.api.examples import EXAMPLE_API10, EXAMPLE_DERIVATION_ID

MIRROR_KEYS = ("derivations", "units")

ENVELOPED = (
    "/v1",
    "/v1/health",
    "/v1/status",
    "/v1/wells",
    f"/v1/wells/{EXAMPLE_API10}",
    f"/v1/wells/{EXAMPLE_API10}/production",
    "/v1/manifests",
    "/v1/conformance",
    "/v1/quarantine",
    "/v1/glossary",
    "/v1/glossary/index",
)


@pytest.mark.parametrize("path", ENVELOPED)
def test_no_response_carries_the_envelope_mirror(client: TestClient, path: str) -> None:
    """S-A: `meta.derivations` and `meta.units` are gone from every served envelope."""
    meta = client.get(path).json()["meta"]

    assert [key for key in MIRROR_KEYS if key in meta] == []
    assert "labels" in meta, "meta.labels is retained — S-A removed the mirror, not the binding"


def test_the_envelope_schema_cannot_readmit_the_mirror(client: TestClient) -> None:
    """A runtime absence check passes on an endpoint that happens not to set it; this does not."""
    meta_schema = client.get("/openapi.json").json()["components"]["schemas"]["MetaModel"]

    assert meta_schema["additionalProperties"] is False
    assert [key for key in MIRROR_KEYS if key in meta_schema["properties"]] == []


def test_the_explain_ref_alias_is_refused(client: TestClient) -> None:
    """S-K: `ref` is not accepted, not even as an alias. Silently ignoring it is the defect."""
    response = client.get("/v1/explain", params={"ref": EXAMPLE_DERIVATION_ID})

    assert response.status_code == 422
    body = response.json()
    assert body["type"].endswith("/validation_failed")
    assert [error for error in body["errors"] if error["pointer"] == "/query/ref"]


def test_the_explain_ref_alias_is_refused_beside_a_valid_handle(client: TestClient) -> None:
    """The failure mode being closed: `h` satisfies the handler and `ref` is dropped unread."""
    response = client.get(
        "/v1/explain", params={"h": EXAMPLE_DERIVATION_ID, "ref": EXAMPLE_DERIVATION_ID}
    )

    assert response.status_code == 422
    error = next(
        error for error in response.json()["errors"] if error["pointer"] == "/query/ref"
    )
    assert error["code"] == "parameter_removed"


def test_the_removed_alias_is_not_in_the_published_document(client: TestClient) -> None:
    """An alias a caller can discover is an alias the caller has to disambiguate (SB-04 E-03)."""
    parameters = client.get("/openapi.json").json()["paths"]["/v1/explain"]["get"]["parameters"]

    assert [parameter["name"] for parameter in parameters if parameter["name"] == "ref"] == []
