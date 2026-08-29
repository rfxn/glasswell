"""SB-08 A-4: the vintages grid's numbers carry the derivation that promoted them.

m-8 measured the R6 walker vacuous on `/v1/vintages` — every numeric leaf allowlisted, no
figure to check. The explorer promotes those numbers to a rendered grid, so they get the
§9.1(b) sidecar the rest of the surface already uses and the four exemptions retire.

The sidecar and the prune are one commit and this file is why: with the sidecar in place the
pruned patterns would cover served figures, and `test_no_exemption_covers_a_served_figure`
fails on any pattern that does.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any

import psycopg
from fastapi.testclient import TestClient

from glasswell.lineage.vintages import open_vintage
from tests.contract.test_naked_numbers import (
    figure_numbers,
    handles,
    naked_numbers,
    payload,
)

SIDECAR_KEYS = {"rows_examined", "rows_appended", "restatement_summary"}
OPENED_AT = datetime(2026, 7, 1, 5, 2, 11, tzinfo=UTC)
UNPROMOTED_ID = "vin_tx_pdq_dsv_2026-07-01"
RESTATED_ID = "vin_nm_ocd_wcproduction_2026-06-01"
RESTATED_MONTH = "2026-03-01"


def collection(client: TestClient) -> list[dict[str, Any]]:
    return client.get("/v1/vintages").json()["data"]


def _open_unpromoted(connection: psycopg.Connection) -> None:
    """A vintage no derivation promoted — the row the sidecar cannot describe."""
    open_vintage(
        connection,
        source_id="tx_pdq_dsv",
        vintage_date=date(2026, 7, 1),
        manifest_ids=[],
        opened_at=OPENED_AT,
        promotion_derivation_id=None,
        rows_examined=7,
        rows_appended=3,
    )


def _open_restated(connection: psycopg.Connection, promotion: str) -> None:
    open_vintage(
        connection,
        source_id="nm_ocd_wcproduction",
        vintage_date=date(2026, 6, 1),
        manifest_ids=[],
        opened_at=OPENED_AT,
        promotion_derivation_id=promotion,
        rows_examined=11,
        rows_appended=5,
        restatement_summary={RESTATED_MONTH: 2},
    )


def test_every_vintage_row_carries_the_derivation_that_promoted_it(client: TestClient) -> None:
    rows = collection(client)

    assert rows
    for row in rows:
        assert row["_lineage"] == dict.fromkeys(SIDECAR_KEYS, row["promotion_derivation_id"])


def test_the_record_carries_the_same_sidecar_as_the_collection_item(client: TestClient) -> None:
    listed = collection(client)[0]

    record = client.get(f"/v1/vintages/{listed['vintage_id']}").json()["data"]

    assert record["_lineage"] == listed["_lineage"]


def test_an_unpromoted_vintage_omits_the_key_rather_than_serving_an_empty_object(
    client: TestClient, seeded: psycopg.Connection
) -> None:
    """`{}` would pass a truthiness check and still exempt nothing: `_sidecar_prefixes`
    iterates the object, so an empty one leaves the numbers under it naked, not covered."""
    _open_unpromoted(seeded)

    row = next(row for row in collection(client) if row["vintage_id"] == UNPROMOTED_ID)

    assert "_lineage" not in row


def test_the_document_declares_the_sidecar_without_requiring_it(client: TestClient) -> None:
    schema = client.get("/openapi.json").json()["components"]["schemas"]["Vintage"]

    assert schema["properties"]["_lineage"]["additionalProperties"] == {"type": "string"}
    assert "_lineage" not in schema.get("required", [])


def test_the_walker_finds_figures_where_m8_measured_none(client: TestClient) -> None:
    """m-8's closure: `/v1/vintages` and `/v1/vintages/{id}` were figure=0, all-allowlisted."""
    listed = payload(client.get("/v1/vintages"))
    record = payload(client.get(f"/v1/vintages/{listed[0]['vintage_id']}"))

    assert {"/0/rows_examined", "/0/rows_appended"} <= set(figure_numbers(listed))
    assert {"/rows_examined", "/rows_appended"} <= set(figure_numbers(record))
    assert naked_numbers(listed) == []
    assert naked_numbers(record) == []


def test_a_restated_vintage_serves_its_counts_under_the_same_handle(
    client: TestClient, seeded: psycopg.Connection
) -> None:
    """The sidecar keys the summary object, not each count: the client resolves by longest
    prefix, so a per-reason count added tomorrow is covered by the entry written today."""
    _open_restated(seeded, collection(client)[0]["promotion_derivation_id"])

    listed = payload(client.get("/v1/vintages"))
    index = next(i for i, row in enumerate(listed) if row["vintage_id"] == RESTATED_ID)

    assert f"/{index}/restatement_summary/{RESTATED_MONTH}" in figure_numbers(listed)
    assert naked_numbers(listed) == []


def test_the_handle_resolves_to_the_promotion_and_the_manifests_it_read(
    client: TestClient,
) -> None:
    """A handle nothing resolves is a naked number with a string beside it (SB-07 §10.3)."""
    row = collection(client)[0]
    found = handles(row)

    assert found == {row["promotion_derivation_id"]}
    chain = client.get("/v1/explain", params={"h": found.pop(), "depth": "full"}).json()
    resolved = chain["data"]["chains"][0]

    assert resolved["root"] == row["promotion_derivation_id"]
    assert set(resolved["terminals"]) == set(row["manifest_ids"])


def test_the_collection_advertises_the_one_call_explain_path(client: TestClient) -> None:
    """SB-04 §2.2: a response that carries handles pre-builds the link that resolves them."""
    body = client.get("/v1/vintages").json()

    assert body["links"]["explain"].startswith("/v1/explain?h=")
    assert "depth=full" in body["links"]["explain"]


def test_the_service_index_serves_the_same_ruling_as_the_vintages_collection(
    client: TestClient,
) -> None:
    """F13: `rows_examined` and `rows_appended` are one quantity from one table. The collection
    gave them a handle and the index gave them an exemption written around the gap — the
    allowlist comment said so outright. Two rulings for one quantity is the defect."""
    published = client.get("/v1").json()["data"]["published_vintages"]
    listed = {row["source_id"]: row for row in collection(client)}

    assert published
    for row in published:
        twin = listed[row["source_id"]]
        assert row["_lineage"]["rows_examined"] == twin["_lineage"]["rows_examined"]
        assert row["_lineage"]["rows_appended"] == twin["_lineage"]["rows_appended"]


def test_the_index_numbers_are_figures_and_not_exemptions(client: TestClient) -> None:
    published = payload(client.get("/v1"))

    assert {"/published_vintages/0/rows_examined", "/published_vintages/0/rows_appended"} <= set(
        figure_numbers(published)
    )
    assert naked_numbers(published) == []
