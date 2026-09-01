"""`/v1/quarantine`: the kitchen is the product (bp:133) — rejects are served, not hidden."""

from __future__ import annotations

from fastapi.testclient import TestClient

from glasswell.api.examples import EXAMPLE_QUARANTINE_ID


def test_rejected_rows_are_listed_with_their_reason(client: TestClient) -> None:
    data = client.get("/v1/quarantine").json()["data"]

    assert len(data) == 4
    assert {item["reason_code"] for item in data} == {
        "unknown_vocab",
        "impossible_volume",
        "confidential_withheld",
    }
    assert all(item["rule_id"] for item in data)


def test_the_collection_filters_on_reason_state_and_stage(client: TestClient) -> None:
    by_reason = client.get("/v1/quarantine", params={"reason_code": "unknown_vocab"}).json()
    by_state = client.get("/v1/quarantine", params={"state": "released"}).json()
    by_stage = client.get("/v1/quarantine", params={"stage": "validate"}).json()

    assert len(by_reason["data"]) == 2
    assert [item["state"] for item in by_state["data"]] == ["released"]
    assert [item["stage"] for item in by_stage["data"]] == ["validate"]


def test_the_collection_orders_by_last_seen(client: TestClient) -> None:
    data = client.get("/v1/quarantine").json()["data"]

    keys = [(item["last_seen_at"], item["quarantine_id"]) for item in data]
    assert keys == sorted(keys, reverse=True)


def test_the_detail_carries_the_rejected_row_and_its_manifests(client: TestClient) -> None:
    """U12: the auditor needs the payload that failed and the file it came from."""
    data = client.get(f"/v1/quarantine/{EXAMPLE_QUARANTINE_ID}").json()["data"]

    assert data["quarantine_id"] == EXAMPLE_QUARANTINE_ID
    assert data["row_payload"]["stream_raw"] == "GasSold"
    assert data["first_seen_manifest_id"].startswith("man_")
    assert data["occurrence_count"] == 3


def test_summary_is_not_shadowed_by_the_detail_route(client: TestClient) -> None:
    """m7: declared before /{id}, or FastAPI matches `summary` as an identifier."""
    response = client.get("/v1/quarantine/summary")

    assert response.status_code == 200
    assert response.json()["data"]["total"] == 4


def test_summary_groups_by_reason_code(client: TestClient) -> None:
    data = client.get("/v1/quarantine/summary").json()["data"]

    groups = {group["key"]: group["count"] for group in data["groups"]}
    assert groups == {"unknown_vocab": 2, "impossible_volume": 1, "confidential_withheld": 1}
    assert data["group_by"] == "reason_code"


def test_summary_groups_by_stage(client: TestClient) -> None:
    data = client.get("/v1/quarantine/summary", params={"group_by": "stage"}).json()["data"]

    assert {group["key"] for group in data["groups"]} == {"conform", "validate"}


def test_summary_filters_by_source(client: TestClient) -> None:
    data = client.get("/v1/quarantine/summary", params={"source_id": "nd_gis_wells"}).json()

    assert data["data"]["total"] == 1


def test_shares_sum_to_one(client: TestClient) -> None:
    data = client.get("/v1/quarantine/summary").json()["data"]

    assert round(sum(group["share"] for group in data["groups"]), 6) == 1.0


def test_an_unknown_quarantine_id_is_not_found(client: TestClient) -> None:
    assert client.get("/v1/quarantine/qr_nothing").status_code == 404


def test_no_reprocess_route_ships_tonight(client: TestClient) -> None:
    document = client.get("/openapi.json").json()

    assert not any("reprocess" in path for path in document["paths"])
