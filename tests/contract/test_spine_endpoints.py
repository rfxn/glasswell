"""The spine endpoints S-K adds, plus DR-33's owner gate on `storage_uri`.

`/v1/vintages` and `/v1/derivations` close two holes the service index already advertised;
`/v1/manifests/{id}/bytes` is SB-07 §9.6's honest boundary between verifiability and
redistribution.
"""

from __future__ import annotations

from pathlib import Path

import psycopg
from fastapi.testclient import TestClient

from glasswell.api.examples import EXAMPLE_DERIVATION_ID, EXAMPLE_MANIFEST_ID
from tests.contract.conftest import RAW_PAYLOAD

PAYLOAD = RAW_PAYLOAD


def test_the_vintage_collection_is_served(client: TestClient) -> None:
    response = client.get("/v1/vintages")

    assert response.status_code == 200
    vintages = response.json()["data"]
    assert vintages
    assert {"vintage_id", "source_id", "vintage_date", "manifest_ids"} <= set(vintages[0])


def test_one_vintage_resolves_by_id(client: TestClient) -> None:
    listed = client.get("/v1/vintages").json()["data"][0]

    response = client.get(f"/v1/vintages/{listed['vintage_id']}")

    assert response.status_code == 200
    assert response.json()["data"]["vintage_id"] == listed["vintage_id"]


def test_an_unknown_vintage_is_a_problem_document(client: TestClient) -> None:
    response = client.get("/v1/vintages/vin_nothing_here")

    assert response.status_code == 404
    assert response.json()["type"].endswith("/not_found")
    assert "vin_nothing_here" in response.json()["detail"], "a route-level 404 would also pass"


def test_the_derivation_collection_the_service_index_advertises_exists(
    client: TestClient,
) -> None:
    """`links.derivations` on `/v1` pointed at a 404 before this endpoint existed."""
    index_link = client.get("/v1").json()["links"]["derivations"]

    response = client.get(index_link)

    assert response.status_code == 200
    assert EXAMPLE_DERIVATION_ID in {row["derivation_id"] for row in response.json()["data"]}


def test_the_owner_can_read_the_raw_bytes(client: TestClient) -> None:
    response = client.get(f"/v1/manifests/{EXAMPLE_MANIFEST_ID}/bytes")

    assert response.status_code == 200
    assert response.content == PAYLOAD
    assert response.headers["ETag"] == f'"sha256:{"e" * 64}"'


def test_a_guest_cannot_read_bytes_that_are_not_redistributable(
    client: TestClient, guest_client: TestClient
) -> None:
    """SB-07 §9.6: the checksum plus the acquisition URL is the auditor's path, not our copy."""
    response = guest_client.get(f"/v1/manifests/{EXAMPLE_MANIFEST_ID}/bytes")

    assert response.status_code == 403
    assert response.json()["type"].endswith("/forbidden")


def test_a_guest_may_read_bytes_the_source_licence_allows(
    client: TestClient, guest_client: TestClient, seeded: psycopg.Connection
) -> None:
    with seeded.cursor() as cursor:
        cursor.execute(
            "update lineage.manifests set redistributable = true where manifest_id = %s",
            (EXAMPLE_MANIFEST_ID,),
        )

    assert guest_client.get(f"/v1/manifests/{EXAMPLE_MANIFEST_ID}/bytes").content == PAYLOAD


def test_bytes_outside_the_raw_root_are_refused(
    client: TestClient, raw_zone: Path, seeded: psycopg.Connection, tmp_path: Path
) -> None:
    """`storage_uri` is a filesystem path; a row that escapes the raw zone serves nothing."""
    escape = tmp_path / "outside.txt"
    escape.write_bytes(b"not in the raw zone")
    with seeded.cursor() as cursor:
        cursor.execute(
            "update lineage.manifests set storage_uri = %s where manifest_id = %s",
            (f"{raw_zone.parent}/../../{escape.name}", EXAMPLE_MANIFEST_ID),
        )

    response = client.get(f"/v1/manifests/{EXAMPLE_MANIFEST_ID}/bytes")

    assert response.status_code == 404
    assert b"not in the raw zone" not in response.content
    assert EXAMPLE_MANIFEST_ID in response.json()["detail"]


def test_missing_bytes_do_not_pretend_to_be_present(
    client: TestClient, raw_zone: Path
) -> None:
    """A row can outlive its file: the raw zone was restored partially, or never copied."""
    raw_zone.unlink()

    response = client.get(f"/v1/manifests/{EXAMPLE_MANIFEST_ID}/bytes")

    assert response.status_code == 404
    assert EXAMPLE_MANIFEST_ID in response.json()["detail"]


def test_the_storage_path_is_owner_only(
    client: TestClient, guest_client: TestClient, agent_client: TestClient
) -> None:
    """DR-33: an absolute server path is deployment detail, not part of the record."""
    owner = client.get(f"/v1/manifests/{EXAMPLE_MANIFEST_ID}").json()["data"]

    assert owner["storage_uri"]
    for other in (guest_client, agent_client):
        body = other.get(f"/v1/manifests/{EXAMPLE_MANIFEST_ID}").json()["data"]
        assert body["storage_uri"] is None
        assert body["sha256"], "verifiability is not what DR-33 gated"
        assert body["acquisition_url"], "verifiability is not what DR-33 gated"


def test_no_storage_path_leaks_through_the_collection(guest_client: TestClient) -> None:
    body = guest_client.get("/v1/manifests").text

    assert "/data/raw" not in body
