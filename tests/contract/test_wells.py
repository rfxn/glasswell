"""`/v1/wells` and `/v1/wells/{api10}` against seeded rows (never against ingest output)."""

from __future__ import annotations

from fastapi.testclient import TestClient

from glasswell.api.examples import EXAMPLE_API10
from tests.contract.conftest import ALL_API10S


def test_the_collection_lists_every_seeded_well(client: TestClient) -> None:
    data = client.get("/v1/wells", params={"limit": 200}).json()["data"]

    assert [item["api10"] for item in data] == sorted(ALL_API10S)


def test_the_collection_filters_on_status(client: TestClient) -> None:
    data = client.get("/v1/wells", params={"status": "plugged"}).json()["data"]

    assert data
    assert {item["status_canonical"] for item in data} == {"plugged"}


def test_the_collection_filters_on_operator(client: TestClient) -> None:
    data = client.get("/v1/wells", params={"operator": "continental"}).json()["data"]

    assert data
    assert all("CONTINENTAL" in item["operator_name_reported"] for item in data)


def test_the_collection_searches_well_names(client: TestClient) -> None:
    data = client.get("/v1/wells", params={"q": "CONTRACT 1H"}).json()["data"]

    assert [item["well_name"] for item in data] == ["CONTRACT 1H"]


def test_the_collection_filters_on_a_bounding_box(client: TestClient) -> None:
    inside = client.get("/v1/wells", params={"bbox": "-104,47.5,-103,48.5"}).json()["data"]
    outside = client.get("/v1/wells", params={"bbox": "-98,46,-97,47"}).json()["data"]

    assert [item["api10"] for item in inside] == [EXAMPLE_API10]
    assert outside == []


def test_an_oversized_bounding_box_is_refused(client: TestClient) -> None:
    response = client.get("/v1/wells", params={"bbox": "-110,40,-100,50"})

    assert response.status_code == 422


def test_a_malformed_bounding_box_is_refused(client: TestClient) -> None:
    assert client.get("/v1/wells", params={"bbox": "-104,47.5,-103"}).status_code == 422


def test_the_detail_carries_the_header_a_card_renders(client: TestClient) -> None:
    data = client.get(f"/v1/wells/{EXAMPLE_API10}").json()["data"]

    assert data["api10"] == EXAMPLE_API10
    assert data["well_name"]
    assert data["operator_name_reported"]
    assert data["status_canonical"]
    assert data["land_unit_label"]
    assert data["spud_date"]
    assert data["confidential_flag"] is False


def test_lateral_length_is_computed_live_from_geometry(client: TestClient) -> None:
    """M6: the mart has no seed helper, so a mart-backed route would be unexercisable."""
    data = client.get(f"/v1/wells/{EXAMPLE_API10}").json()["data"]

    assert data["lateral_count"] == 1
    figure = data["lateral_length_ft"]
    assert figure["unit"] == "ft"
    assert figure["d"].startswith("drv_")
    assert 9000 < float(figure["value"]) < 12000


def test_the_detail_names_its_geometry_and_how_length_was_measured(client: TestClient) -> None:
    data = client.get(f"/v1/wells/{EXAMPLE_API10}").json()["data"]

    assert {item["geom_type"] for item in data["geometry"]} == {"lateral", "surface"}
    # A3-F1: no zone is chosen, so the computation is defined on the storage CRS itself.
    assert data["length_method"] == "geodesic"
    assert data["compute_crs"] == "EPSG:4326"
    assert data["storage_crs"] == "EPSG:4326"


def test_the_detail_links_to_its_sub_resources(client: TestClient) -> None:
    body = client.get(f"/v1/wells/{EXAMPLE_API10}").json()

    assert body["links"]["self"] == f"/v1/wells/{EXAMPLE_API10}"
    assert body["links"]["production"] == f"/v1/wells/{EXAMPLE_API10}/production"


def test_a_well_with_no_geometry_still_serves(client: TestClient) -> None:
    data = client.get("/v1/wells/3305300003").json()["data"]

    assert data["lateral_count"] == 0
    assert data["lateral_length_ft"] is None
    assert data["surface_point"] is None


def test_an_as_of_before_the_effective_date_hides_the_well(client: TestClient) -> None:
    response = client.get(f"/v1/wells/{EXAMPLE_API10}", params={"as_of": "2026-07-01"})

    assert response.status_code == 404


def test_the_resolved_as_of_is_reported(client: TestClient) -> None:
    meta = client.get(f"/v1/wells/{EXAMPLE_API10}").json()["meta"]

    assert meta["as_of"]["requested"] == "latest"
    assert meta["as_of"]["resolved"] == "2026-08-01"


def test_labels_bind_fields_to_glossary_terms(client: TestClient) -> None:
    labels = client.get(f"/v1/wells/{EXAMPLE_API10}").json()["meta"]["labels"]

    assert labels["/api10"] == "gt_api_10_api_12_api_14"
    assert labels["/land_unit_label"] == "gt_land_unit"
