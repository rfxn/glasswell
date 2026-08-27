"""Current-snapshot ND physical-neighbour route semantics and lineage handles."""

from __future__ import annotations

from fastapi.testclient import TestClient

from glasswell.api.examples import EXAMPLE_API10
from glasswell.api.routers.neighbors import _warnings
from glasswell.lineage.serialization import hash_payload
from glasswell.marts.neighbors import resident_content_identity

PATH = f"/v1/wells/{EXAMPLE_API10}/neighbors"


def test_neighbor_formation_warnings_point_to_the_exact_counted_bucket() -> None:
    warnings = _warnings(
        {
            "missing_completion_anchor": 0,
            "formation_unavailable": 2,
            "formation_conflicts": 3,
        }
    )

    assert warnings == [
        {
            "code": "neighbor_formation_unavailable",
            "detail": (
                "2 spatial candidates have unavailable earliest-pool formation context;"
                " no formation was inferred."
            ),
            "pointer": "/coverage/formation_unavailable",
        },
        {
            "code": "neighbor_formation_conflict",
            "detail": (
                "3 spatial candidates have conflicting earliest-pool formation context;"
                " no formation was selected."
            ),
            "pointer": "/coverage/formation_conflicts",
        },
    ]


def test_neighbor_fixture_derivation_matches_its_exact_persisted_content(seeded) -> None:
    subject_rows, subject_digest, edge_rows, edge_digest = resident_content_identity(seeded)
    expected_digest = hash_payload(
        {
            "subjects": {"rows": subject_rows, "sha256": subject_digest},
            "edges": {"rows": edge_rows, "sha256": edge_digest},
        }
    )
    with seeded.cursor() as cursor:
        cursor.execute(
            "select distinct d.output_rows, d.output_sha256"
            " from marts.nd_neighbor_subjects s"
            " join lineage.derivations d on d.derivation_id = s.derivation_id"
        )
        identities = cursor.fetchall()

    assert identities == [(subject_rows + edge_rows, expected_digest)]


def test_neighbors_are_minimum_distance_ordered_and_explicitly_not_analogs(
    client: TestClient,
) -> None:
    response = client.get(PATH)

    assert response.status_code == 200, response.text
    body = response.json()
    data = body["data"]
    assert data["relation"] == "physical_neighbours_not_model_analogs"
    assert data["geometry_scope"] == "current_only"
    assert [row["neighbor_api10"] for row in data["neighbors"]] == [
        "3305399998",
        "3305399999",
    ]
    assert [row["distance_ft"]["value"] for row in data["neighbors"]] == [
        "2624.67",
        "3280.84",
    ]
    assert data["coverage"]["spatial_candidates"]["value"] == "2"
    assert data["coverage"]["eligible"]["value"] == "2"
    assert data["coverage"]["returned"]["value"] == "2"
    assert body["links"]["well"] == f"/v1/wells/{EXAMPLE_API10}"


def test_neighbors_use_a_strict_completion_cut_and_exclude_equality(client: TestClient) -> None:
    body = client.get(PATH, params={"at_date": "2025-10-10"}).json()["data"]

    assert [row["neighbor_api10"] for row in body["neighbors"]] == ["3305399998"]
    assert body["at_date_source"] == "caller_supplied"
    assert body["coverage"]["on_or_after_cut"]["value"] == "1"
    assert body["coverage"]["eligible"]["value"] == "1"


def test_neighbor_filters_never_infer_an_unmatched_formation(client: TestClient) -> None:
    matched = client.get(PATH, params={"formation_id": "bakken"}).json()["data"]
    unmatched = client.get(PATH, params={"formation_id": "three_forks"}).json()["data"]

    assert len(matched["neighbors"]) == 2
    assert unmatched["neighbors"] == []
    assert unmatched["coverage"]["eligible"]["value"] == "0"


def test_neighbor_cursor_pins_the_subject_and_resolved_cut(client: TestClient) -> None:
    first = client.get(PATH, params={"limit": 1}).json()
    cursor = first["meta"]["next_cursor"]

    second = client.get(PATH, params={"limit": 1, "cursor": cursor})
    changed_cut = client.get(
        PATH,
        params={"limit": 1, "cursor": cursor, "at_date": "2025-10-10"},
    )
    other_subject = client.get(
        "/v1/wells/3305399998/neighbors", params={"limit": 1, "cursor": cursor}
    )

    assert second.status_code == 200
    assert second.json()["data"]["neighbors"][0]["neighbor_api10"] == "3305399999"
    assert changed_cut.status_code == 422
    assert changed_cut.json()["type"] == "/v1/errors/cursor_query_mismatch"
    assert other_subject.status_code == 422
    assert other_subject.json()["type"] == "/v1/errors/cursor_query_mismatch"


def test_neighbor_geometry_refuses_a_historical_snapshot(client: TestClient) -> None:
    response = client.get(PATH, params={"as_of": "2026-08-01"})

    assert response.status_code == 422
    assert response.json()["errors"][0]["code"] == "current_only_geometry"


def test_missing_subject_completion_requires_an_explicit_cut(
    client: TestClient, seeded
) -> None:
    with seeded.cursor() as cursor:
        cursor.execute(
            "update marts.nd_neighbor_subjects set completion_date = null where api10 = %s",
            (EXAMPLE_API10,),
        )

    refused = client.get(PATH)
    supplied = client.get(PATH, params={"at_date": "2025-12-20"})

    assert refused.status_code == 422
    assert refused.json()["errors"][0]["code"] == "completion_anchor_required"
    assert supplied.status_code == 200


def test_neighbor_handles_validate_exact_persisted_rows(client: TestClient) -> None:
    data = client.get(PATH).json()["data"]
    neighbor = data["neighbors"][0]
    handle = neighbor["distance_ft"]["d"]
    coverage_handle = data["coverage"]["eligible"]["d"]

    valid = client.get("/v1/explain", params={"h": handle})
    missing = client.get(
        "/v1/explain",
        params={"h": handle.replace("neighbor_api10=3305399998", "neighbor_api10=3305399997")},
    )
    wrong_column = client.get(
        "/v1/explain", params={"h": handle.replace("col=distance_m", "col=api10")}
    )
    coverage = client.get("/v1/explain", params={"h": coverage_handle})
    wrong_metric = client.get(
        "/v1/explain",
        params={"h": coverage_handle.replace("metric=eligible", "metric=estimated")},
    )

    assert valid.status_code == 200, valid.text
    assert missing.status_code == 404
    assert missing.json()["stop_reason"] == "unknown_id"
    assert wrong_column.status_code == 422
    assert wrong_column.json()["type"] == "/v1/errors/selector_ambiguous"
    assert coverage.status_code == 200, coverage.text
    assert wrong_metric.status_code == 422
