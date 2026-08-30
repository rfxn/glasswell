"""`/v1/wells` and `/v1/wells/{api10}` against seeded rows (never against ingest output)."""

from __future__ import annotations

from datetime import date

import psycopg
from fastapi.testclient import TestClient

import glasswell.api.routers.wells as wells_router
from glasswell.api.examples import EXAMPLE_API10
from glasswell.lineage.ids import parse_handle
from tests.contract.conftest import ALL_API10S, TX_API10


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


def test_the_name_search_does_not_resolve_an_api10_and_says_so_by_returning_nothing(
    client: TestClient,
) -> None:
    """Why the identity filter exists rather than a widened `q`: a name search handed an
    identifier cannot answer, and the served semantics say to use `api10` for that."""
    assert client.get("/v1/wells", params={"q": EXAMPLE_API10}).json()["data"] == []


def test_the_collection_resolves_the_identity_spine_whole_and_never_as_a_fragment(
    client: TestClient,
) -> None:
    found = client.get("/v1/wells", params={"api10": EXAMPLE_API10}).json()["data"]

    assert [item["api10"] for item in found] == [EXAMPLE_API10]
    assert client.get("/v1/wells", params={"api10": "3305399999"}).json()["data"] == []
    # A fragment is refused at the grammar rather than answered as a prefix search.
    assert client.get("/v1/wells", params={"api10": "330531"}).status_code == 422


def test_the_identity_filter_takes_the_api14_literal_the_well_carries(
    client: TestClient,
) -> None:
    """API-14 normalises to API-10 for joins, and the well's own recorded literal is that join —
    which digits make the API-10 is an identity rule's declaration, not this route's."""
    found = client.get("/v1/wells", params={"api10": f"{EXAMPLE_API10}0000"}).json()["data"]

    assert [item["api10"] for item in found] == [EXAMPLE_API10]
    assert client.get("/v1/wells", params={"api10": f"{EXAMPLE_API10}9999"}).json()["data"] == []


def test_the_collection_filters_on_a_bounding_box(client: TestClient) -> None:
    inside = client.get("/v1/wells", params={"bbox": "-104,47.5,-103,48.5"}).json()["data"]
    outside = client.get("/v1/wells", params={"bbox": "-98,46,-97,47"}).json()["data"]

    assert [item["api10"] for item in inside] == [EXAMPLE_API10]
    assert outside == []


def test_the_collection_filters_on_the_well_type_code_verbatim(client: TestClient) -> None:
    """R-1 after M1-7: the disposal layer scopes the spine by the code as filed — no decode,
    no classing, and no case-folding, because the code is the regulator's spelling."""
    producing = client.get("/v1/wells", params={"well_type": "PRODUCING"}).json()["data"]
    og = client.get("/v1/wells", params={"well_type": "OG"}).json()["data"]

    assert [item["api10"] for item in producing] == [TX_API10]
    assert [item["api10"] for item in og] == sorted(set(ALL_API10S) - {TX_API10})
    assert client.get("/v1/wells", params={"well_type": "producing"}).json()["data"] == []
    assert client.get("/v1/wells", params={"well_type": "SWD"}).json()["data"] == []


def test_the_collection_filters_on_geometry_provenance_verbatim(client: TestClient) -> None:
    """m13 residual, the R-1 pattern replayed for provenance: the class as canonical records
    it — no decode, no case-folding — and a well matches on any of its geometry."""
    lateral = client.get("/v1/wells", params={"geometry_provenance": "lateral"}).json()["data"]
    surface = client.get("/v1/wells", params={"geometry_provenance": "surface"}).json()["data"]

    assert [item["api10"] for item in lateral] == [EXAMPLE_API10]
    assert [item["api10"] for item in surface] == sorted((EXAMPLE_API10, TX_API10))
    assert (
        client.get("/v1/wells", params={"geometry_provenance": "LATERAL"}).json()["data"] == []
    )
    assert (
        client.get("/v1/wells", params={"geometry_provenance": "survey_trace"}).json()["data"]
        == []
    )


def test_status_summary_bounds_provenance_writes_per_principal(
    client: TestClient, monkeypatch
) -> None:
    monkeypatch.setattr(wells_router, "STATUS_SUMMARY_REQUESTS_PER_MINUTE", 1)

    first = client.get("/v1/wells/status-summary", params={"bbox": "-104,46,-103,47"})
    refused = client.get(
        "/v1/wells/status-summary", params={"bbox": "-104.1,46,-103,47"}
    )

    assert first.status_code == 200
    assert refused.status_code == 429
    assert refused.json()["type"].endswith("/rate_limited")


def test_the_collection_serves_each_wells_provenance_classes(client: TestClient) -> None:
    """The payload column beside the filter: every class the well's geometry carries,
    alphabetical, and an empty list where no geometry is recorded at all."""
    by_api10 = {
        item["api10"]: item["geometry_provenance"]
        for item in client.get("/v1/wells", params={"limit": 200}).json()["data"]
    }

    assert by_api10[EXAMPLE_API10] == ["lateral", "surface"]
    assert by_api10[TX_API10] == ["surface"]
    assert [classes for classes in by_api10.values() if classes == []], (
        "a well with no geometry must serve an empty list, not vanish"
    )


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


def test_a_backdated_crs_route_waits_for_its_publication_clock(
    client: TestClient, seeded: psycopg.Connection
) -> None:
    with seeded.cursor() as cursor:
        cursor.execute(
            "insert into lineage.crs_registry"
            " (basin, compute_epsg, storage_epsg, effective_from, note, length_rule_source,"
            " published_vintage) values"
            " ('williston', 32613, 4326, %s, 'future routing fixture',"
            " 'tx_gis_wells_county', %s)",
            (date(2026, 8, 1), date(2026, 9, 1)),
        )
    seeded.commit()

    before = client.get(
        f"/v1/wells/{EXAMPLE_API10}", params={"as_of": "2026-08-28"}
    ).json()["data"]
    after = client.get(
        f"/v1/wells/{EXAMPLE_API10}", params={"as_of": "2026-09-01"}
    ).json()["data"]

    assert (before["length_method"], before["compute_crs"]) == ("geodesic", "EPSG:4326")
    assert (after["length_method"], after["compute_crs"]) == ("geodesic", "EPSG:4326")
    derivations = {
        "before": parse_handle(before["lateral_length_ft"]["d"]).derivation_id,
        "after": parse_handle(after["lateral_length_ft"]["d"]).derivation_id,
    }
    with seeded.cursor() as cursor:
        cursor.execute(
            "select derivation_id, rule_id from lineage.derivation_rules"
            " where derivation_id = any(%s)",
            (list(derivations.values()),),
        )
        rules = dict(cursor.fetchall())
    assert rules[derivations["before"]] == "cr_nd_compute_crs_2"
    assert rules[derivations["after"]] == "cr_tx_compute_crs_1"


def test_the_detail_links_to_its_sub_resources(client: TestClient) -> None:
    body = client.get(f"/v1/wells/{EXAMPLE_API10}").json()

    assert body["links"]["self"] == f"/v1/wells/{EXAMPLE_API10}"
    assert body["links"]["production"] == f"/v1/wells/{EXAMPLE_API10}/production"
    assert body["links"]["neighbors"] == f"/v1/wells/{EXAMPLE_API10}/neighbors"


def test_a_well_with_no_geometry_still_serves(client: TestClient) -> None:
    body = client.get("/v1/wells/3305300003").json()
    data = body["data"]

    assert data["lateral_count"] == 0
    assert data["lateral_length_ft"] is None
    assert data["surface_point"] is None
    assert "neighbors" not in body["links"]


def test_an_as_of_before_the_effective_date_hides_the_well(client: TestClient) -> None:
    response = client.get(f"/v1/wells/{EXAMPLE_API10}", params={"as_of": "2026-07-01"})

    assert response.status_code == 404


def test_the_resolved_as_of_is_reported(client: TestClient) -> None:
    meta = client.get(f"/v1/wells/{EXAMPLE_API10}").json()["meta"]

    assert meta["as_of"]["requested"] == "latest"
    assert meta["as_of"]["resolved"] == "2026-08-20"


def test_labels_bind_fields_to_glossary_terms(client: TestClient) -> None:
    labels = client.get(f"/v1/wells/{EXAMPLE_API10}").json()["meta"]["labels"]

    assert labels["/api10"] == "gt_api_10_api_12_api_14"
    assert labels["/land_unit_label"] == "gt_land_unit"
