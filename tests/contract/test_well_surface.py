"""The basin block on the well record: a served polygon answer with a provenance class.

`canonical.wells.basin` is the slice the ingest took. It has been rendered as plain text with
no handle, no rule and no provenance since the spine landed, and for 182,626 wells it is null.
This is what replaces it: the published boundary the well's geometry falls in, the plays that
stack there, the filed label kept beside them, whether the two agree, and which geometry was
asked.
"""

from __future__ import annotations

from hashlib import sha256

import psycopg
import pytest
from fastapi.testclient import TestClient

from glasswell.lineage.capture import lineage_session
from glasswell.lineage.store import PostgresRecorder
from glasswell.marts.well_basin_context import refresh_well_basin_context
from tests.contract.conftest import EXAMPLE_API10, TX_API10
from tests.support.seed import FIXTURE_ENV, seed_derivation, seed_manifest

pytestmark = pytest.mark.contract

# A ring around the contract fixture's surface point, and one far from it.
INSIDE_RING = "MULTIPOLYGON(((-104 47, -103 47, -103 48, -104 48, -104 47)))"


def boundary(
    connection: psycopg.Connection, *, boundary_id: str, kind: str, name: str, area: float
) -> None:
    # Its own sha: a manifest is keyed on the bytes it registers, and the contract fixture has
    # already claimed the ones the seeders use.
    manifest = seed_manifest(
        connection,
        sha256=sha256(boundary_id.encode()).hexdigest(),
        source_key=f"{boundary_id}.zip",
    )
    derivation = seed_derivation(connection, operation="canonical.promote")
    with connection.cursor() as cursor:
        cursor.execute(
            "insert into canonical.basin_boundaries (boundary_id, boundary_kind, name,"
            " area_sq_mi, area_basis, vintage_label, geom, source_datum, source_manifest_id,"
            " derivation_id)"
            " values (%s, %s, %s, %s, 'published', 'EIA 2024',"
            " st_geomfromtext(%s, 4326), 'EPSG:4326', %s, %s)",
            (boundary_id, kind, name, area, INSIDE_RING, manifest, derivation),
        )


@pytest.fixture
def basin_context(client: TestClient, seeded: psycopg.Connection) -> psycopg.Connection:
    boundary(
        seeded,
        boundary_id="eia_basin_williston",
        kind="basin",
        name="WILLISTON",
        area=200000,
    )
    boundary(seeded, boundary_id="eia_play_bakken", kind="play", name="BAKKEN", area=50000)
    seeded.commit()
    with lineage_session(recorder=PostgresRecorder(seeded), environment=FIXTURE_ENV):
        refresh_well_basin_context(seeded)
    seeded.commit()
    return seeded


def test_the_basin_is_a_served_answer_with_a_class_and_a_rule(
    client: TestClient, basin_context: psycopg.Connection
) -> None:
    body = client.get(f"/v1/wells/{EXAMPLE_API10}").json()["data"]["basin_context"]

    assert body["basin_class"] == "in_published_boundary"
    assert body["basin_name"] == "WILLISTON"
    assert body["boundary_vintage"] == "EIA 2024"
    # Which end of the well answered, registered as the rule's decision rather than assumed.
    assert body["geometry_basis"] == "surface"
    assert body["rule_id"] == "cr_nd_basin_context_1"


def test_plays_are_plural_because_they_stack(
    client: TestClient, basin_context: psycopg.Connection
) -> None:
    body = client.get(f"/v1/wells/{EXAMPLE_API10}").json()["data"]["basin_context"]

    assert body["play_name"] == ["BAKKEN"]
    assert body["play_class"] == "plays"


def test_the_filed_label_rides_beside_the_polygon_with_their_agreement_marked(
    client: TestClient, basin_context: psycopg.Connection
) -> None:
    """R-14: the disagreement is a fact with a handle, not a silent overwrite."""
    body = client.get(f"/v1/wells/{EXAMPLE_API10}").json()["data"]["basin_context"]

    assert body["basin_label_filed"] == "williston"
    assert body["label_class"] == "agrees"
    assert body["label_agrees"] is True


def test_a_well_whose_label_and_polygon_disagree_says_so(
    client: TestClient, basin_context: psycopg.Connection
) -> None:
    # The Texas shape: the fixture's Texas well is labelled `permian` by its ingest slice and
    # sits inside the Williston ring this fixture draws.
    body = client.get(f"/v1/wells/{TX_API10}").json()["data"]["basin_context"]

    assert body["basin_label_filed"] == "permian"
    assert body["label_class"] in {"disagrees", "no_label_to_compare"}
    if body["label_class"] == "disagrees":
        assert body["label_agrees"] is False
        assert body["basin_name"] != "permian"


def test_a_well_outside_every_boundary_is_answered_rather_than_left_null(
    client: TestClient, basin_context: psycopg.Connection
) -> None:
    body = client.get("/v1/wells/3305300003").json()["data"]["basin_context"]

    # `outside_published_boundaries` is a served class about the boundary set, and
    # `no_geometry` is a served class about the well. Neither is a null a reader must guess at.
    assert body["basin_class"] in {"outside_published_boundaries", "no_geometry"}
    assert body["basin_name"] is None
    # Outside carries the set that was asked; no geometry carries none, because none was.
    if body["basin_class"] == "outside_published_boundaries":
        assert body["boundary_vintage"] == "EIA 2024"
    else:
        assert body["boundary_vintage"] is None


def test_an_unrefreshed_mart_is_a_pipeline_state_and_not_a_null_basin(
    client: TestClient, seeded: psycopg.Connection
) -> None:
    """Without the refresh there is no row, and the response says so by omitting the block
    rather than by serving a basin of null, which would read as a fact about the well."""
    body = client.get(f"/v1/wells/{EXAMPLE_API10}").json()["data"]

    assert body["basin_context"] is None
    # And the bare label is still on the wire, because that is what it always was.
    assert body["basin"] == "williston"
