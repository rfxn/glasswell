"""Per-class arithmetic for `/v1/wells/status-summary`, against a population it can count.

The contract fixture holds two wells, both active, which proves the shape and nothing about
the sum. This file seeds a population with several classes, a well the source reported no
status for, a restated status and a well outside the box — the four ways a legend count goes
wrong — and asks the endpoint for the number a reader would count by hand.

It also holds the plan: the box predicate has to be answerable from
`well_spatial_geom_idx`, because the deployed slice aggregates over 43,817 ND and 355,463 TX
points on every viewport settle.
"""

from __future__ import annotations

import json
from datetime import date
from typing import Any

import psycopg
import pytest
from fastapi.testclient import TestClient

from glasswell.api.routers.wells import STATUS_SUMMARY_SQL
from glasswell.seed import seed_all
from tests.support.seed import seed_manifest, seed_well, seed_well_spatial

SUMMARY = "/v1/wells/status-summary"
# A box over the seeded ND cluster. Every point below sits inside it except OUTSIDE.
BOX = "-104,47,-103,48"
WIDE = "-180,-90,180,90"

# api10, status, longitude. Four classes, one absence, one well beyond the box.
ND_POPULATION: tuple[tuple[str, str | None, float], ...] = (
    ("3305300001", "active", -103.90),
    ("3305300002", "active", -103.80),
    ("3305300003", "active", -103.70),
    ("3305300004", "plugged", -103.60),
    ("3305300005", "plugged", -103.50),
    ("3305300006", "dry", -103.40),
    ("3305300007", None, -103.30),
    ("3305300008", None, -103.20),
)
OUTSIDE = ("3305300009", "inactive", -101.00)
TX_WELL = ("4200300001", "service", -102.50, 32.30)
LATITUDE = 47.50


@pytest.fixture
def population(db: psycopg.Connection) -> psycopg.Connection:
    """One manifest, one derivation, nine ND wells and a TX well with a surface hole each."""
    seed_all(db)
    manifest = seed_manifest(db, sha256="c" * 64, source_id="nd_gis_wells", source_key="wells.zip")
    for api10, status, longitude in (*ND_POPULATION, OUTSIDE):
        seed_well(db, api10=api10, manifest_id=manifest, status_canonical=status)
        seed_well_spatial(
            db,
            api10=api10,
            geom_type="surface",
            wkt=f"POINT({longitude} {LATITUDE})",
            manifest_id=manifest,
        )
    api10, status, longitude, latitude = TX_WELL
    seed_well(
        db,
        api10=api10,
        manifest_id=manifest,
        state_code="42",
        basin="permian",
        status_canonical=status,
    )
    seed_well_spatial(
        db,
        api10=api10,
        geom_type="surface",
        wkt=f"POINT({longitude} {latitude})",
        manifest_id=manifest,
    )
    db.commit()
    return db


def summary(client: TestClient, bbox: str = BOX, **params: Any) -> dict[str, Any]:
    response = client.get(SUMMARY, params={"bbox": bbox, **params})
    assert response.status_code == 200, response.text
    return response.json()


def counts(data: dict[str, Any]) -> dict[str, int]:
    """The legend's own reading of the response: one number per class it can draw."""
    found = {row["status"]: int(row["wells"]["value"]) for row in data["statuses"]}
    if data["unmapped_wells"] is not None:
        found["unmapped"] = int(data["unmapped_wells"]["value"])
    return found


def test_every_class_in_the_box_is_counted_once(
    population: psycopg.Connection, api_client: TestClient
) -> None:
    data = summary(api_client)["data"]

    assert counts(data) == {"active": 3, "plugged": 2, "dry": 1, "unmapped": 2}
    assert data["wells"]["value"] == "8"


def test_the_absence_class_is_its_own_bucket_and_never_folded_into_one(
    population: psycopg.Connection, api_client: TestClient
) -> None:
    """65,685 Texas wells carry no status because the RRC reported none. Adding them to any
    class would overstate it, and dropping them would make the parts stop summing to the whole.
    """
    data = summary(api_client)["data"]

    assert {row["status"] for row in data["statuses"]} == {"active", "plugged", "dry"}
    assert data["unmapped_wells"]["value"] == "2"
    assert sum(int(row["wells"]["value"]) for row in data["statuses"]) + 2 == int(
        data["wells"]["value"]
    )


def test_a_well_outside_the_box_is_not_counted(
    population: psycopg.Connection, api_client: TestClient
) -> None:
    inside = counts(summary(api_client)["data"])
    everywhere = counts(summary(api_client, WIDE)["data"])

    assert "inactive" not in inside
    assert everywhere["inactive"] == 1


def test_the_count_does_not_move_when_the_box_grows_around_the_same_wells(
    population: psycopg.Connection, api_client: TestClient
) -> None:
    """The defect this endpoint replaces, stated as an assertion: the drawn-feature count fell
    as the viewport widened. A data count is monotone — a wider box never holds fewer wells."""
    tight = int(summary(api_client, "-103.95,47.4,-103.15,47.6")["data"]["wells"]["value"])
    wide = int(summary(api_client, WIDE)["data"]["wells"]["value"])

    assert tight == 8
    assert wide == 10


def test_the_texas_wells_are_counted_under_their_own_vocabulary(
    population: psycopg.Connection, api_client: TestClient
) -> None:
    basins = {row["state_code"]: row for row in summary(api_client, WIDE)["data"]["basins"]}

    assert basins["42"]["status_vocabulary_rule"] == "cr_tx_status_vocab_1"
    assert basins["33"]["status_vocabulary_rule"] == "cr_nd_status_vocab_1"
    assert [row["status"] for row in basins["42"]["statuses"]] == ["service"]
    assert basins["33"]["unmapped_wells"]["value"] == "2"
    assert basins["42"]["unmapped_wells"] is None


def test_the_basin_rows_sum_to_the_total(
    population: psycopg.Connection, api_client: TestClient
) -> None:
    data = summary(api_client, WIDE)["data"]

    assert sum(int(row["wells"]["value"]) for row in data["basins"]) == int(
        data["wells"]["value"]
    )


def test_a_restated_status_is_read_at_the_knowledge_time_asked_for(
    population: psycopg.Connection, api_client: TestClient
) -> None:
    """M13: a status change appends a row. The legend at a past `as_of` shows the classes that
    were true then, not today's classes over yesterday's wells."""
    seed_well(
        population,
        api10=ND_POPULATION[0][0],
        effective_from=date(2026, 9, 1),
        status_canonical="plugged",
    )
    population.commit()

    now = counts(summary(api_client, as_of="2026-09-30")["data"])
    before = counts(summary(api_client, as_of="2026-08-15")["data"])

    assert now == {"active": 2, "plugged": 3, "dry": 1, "unmapped": 2}
    assert before == {"active": 3, "plugged": 2, "dry": 1, "unmapped": 2}


def test_the_resolved_vintage_is_the_latest_row_the_counts_were_taken_from(
    population: psycopg.Connection, api_client: TestClient
) -> None:
    seed_well(
        population,
        api10=ND_POPULATION[0][0],
        effective_from=date(2026, 9, 1),
        status_canonical="plugged",
    )
    population.commit()

    assert summary(api_client)["meta"]["as_of"]["resolved"] == "2026-09-01"
    assert summary(api_client, as_of="2026-08-15")["meta"]["as_of"]["resolved"] == "2026-08-01"


def test_geometry_whose_well_row_is_missing_is_disclosed_not_classed(
    population: psycopg.Connection, api_client: TestClient
) -> None:
    """A promoted geometry whose api10 never reached the spine draws on the map with no
    status. Counting it as unmapped would make an absent well row look like an absent status.
    """
    seed_well_spatial(
        population,
        api10="3305399999",
        geom_type="surface",
        wkt=f"POINT(-103.25 {LATITUDE})",
        manifest_id=seed_manifest(population, sha256="f" * 64, source_id="nd_gis_wells"),
    )
    population.commit()

    body = summary(api_client)
    warnings = {item["code"]: item["detail"] for item in body["meta"]["warnings"]}

    assert counts(body["data"]) == {"active": 3, "plugged": 2, "dry": 1, "unmapped": 2}
    assert "1 geometry" in warnings["geometry_without_a_well_row"]


def test_every_count_addresses_itself_and_the_handles_are_distinct(
    population: psycopg.Connection, api_client: TestClient
) -> None:
    """A shared handle would explain the box, not the bucket: `?h=` has to answer "where did
    *this* number come from", one bucket at a time."""
    data = summary(api_client, WIDE)["data"]
    addressed = [row["wells"]["d"] for row in data["statuses"]] + [data["wells"]["d"]]

    assert len(set(addressed)) == len(addressed)
    assert all("#col=wells" in handle for handle in addressed)
    assert "&status=active&" in next(
        row["wells"]["d"] for row in data["statuses"] if row["status"] == "active"
    )


def test_the_box_predicate_can_be_answered_from_the_geometry_index(
    population: psycopg.Connection, api_client: TestClient
) -> None:
    """The performance claim, as a test rather than a paragraph. Seeded row counts are far
    below the point where the planner would choose an index, so the sequential path is turned
    off and the question asked is the one that matters at 400,000 points: can this predicate
    use the GiST index at all, or is it written in a way that cannot?
    """
    parameters = {"minx": -104.0, "miny": 47.0, "maxx": -103.0, "maxy": 48.0, "as_of": None}
    with population.cursor() as cursor:
        cursor.execute("set enable_seqscan = off")
        cursor.execute(f"explain (format json) {STATUS_SUMMARY_SQL}", parameters)
        plan = json.dumps(cursor.fetchone()[0])
        cursor.execute("set enable_seqscan = on")

    assert "well_spatial_geom_idx" in plan
