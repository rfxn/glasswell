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
from tests.support.seed import (
    FIXTURE_ENV,
    seed_derivation,
    seed_manifest,
    seed_well_spatial,
)

pytestmark = pytest.mark.contract

# A ring around the contract fixture's North Dakota surface point, and one around its Texas
# one. Both are drawn so every branch of the classifier is exercised exactly, rather than
# asserted with an `in {...}` that passes either way (gate H-15).
INSIDE_RING = "MULTIPOLYGON(((-104 47, -103 47, -103 48, -104 48, -104 47)))"
TEXAS_RING = "MULTIPOLYGON(((-103.5 32, -102 32, -102 33, -103.5 33, -103.5 32)))"
# Nebraska, where the fixture draws no boundary at all.
OUTSIDE_POINT = "POINT(-100.0 41.0)"
OUTSIDE_WELL = "3305300002"


def boundary(
    connection: psycopg.Connection,
    *,
    boundary_id: str,
    kind: str,
    name: str,
    area: float,
    wkt: str = INSIDE_RING,
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
            (boundary_id, kind, name, area, wkt, manifest, derivation),
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
    # The Texas well's own polygon, which is not the `permian` its ingest slice filed: this is
    # the disagreement the section exists to serve, and the fixture makes it exact.
    boundary(
        seeded,
        boundary_id="eia_basin_fort_worth",
        kind="basin",
        name="FORT WORTH",
        area=15000,
        wkt=TEXAS_RING,
    )
    # And a well with a surface point no boundary contains, so `outside_published_boundaries`
    # is exercised as itself rather than shared with `no_geometry`.
    seed_well_spatial(seeded, api10=OUTSIDE_WELL, geom_type="surface", wkt=OUTSIDE_POINT)
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


def test_every_served_basin_block_names_the_rule_that_decided_it(
    client: TestClient, basin_context: psycopg.Connection
) -> None:
    """R8 where a reader meets it: a basin decision with no rule is a mapping that exists only
    in code. Every Texas card served `rule_id: null` for the life of the v0.80 supersession,
    which carried nine of its decisions forward and not `basin_context`, and the only rule_id
    assertion in this suite named North Dakota. Read off the mart rather than a list of wells,
    so a jurisdiction added to the fixture is covered by writing no test at all.
    """
    with basin_context.cursor() as cursor:
        cursor.execute("select api10 from marts.well_basin_context order by api10")
        served = [row[0] for row in cursor.fetchall()]
    assert served, "the fixture served no basin rows"

    silent = [
        api10
        for api10 in served
        if client.get(f"/v1/wells/{api10}").json()["data"]["basin_context"]["rule_id"] is None
    ]

    assert silent == [], f"served basin blocks naming no rule: {silent}"


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
    # The Texas shape, exactly: the fixture's Texas well is labelled `permian` by its ingest
    # slice and its surface point falls in the Fort Worth ring.
    body = client.get(f"/v1/wells/{TX_API10}").json()["data"]["basin_context"]

    assert body["basin_label_filed"] == "permian"
    assert body["basin_name"] == "FORT WORTH"
    assert body["label_class"] == "disagrees"
    assert body["label_agrees"] is False


def test_a_well_outside_every_boundary_is_answered_rather_than_left_null(
    client: TestClient, basin_context: psycopg.Connection
) -> None:
    body = client.get(f"/v1/wells/{OUTSIDE_WELL}").json()["data"]["basin_context"]

    # A served class about the boundary set, not a null a reader has to guess at, and it names
    # the set that was asked.
    assert body["basin_class"] == "outside_published_boundaries"
    assert body["basin_name"] is None
    assert body["boundary_vintage"] == "EIA 2024"


def test_a_well_with_no_geometry_is_a_different_answer_from_outside(
    client: TestClient, basin_context: psycopg.Connection
) -> None:
    body = client.get("/v1/wells/3305300003").json()["data"]["basin_context"]

    # Nothing was asked, so no boundary set is named: `no_geometry` is a fact about the well
    # where `outside_published_boundaries` is a fact about the published set.
    assert body["basin_class"] == "no_geometry"
    assert body["geometry_basis"] == "no_geometry"
    assert body["boundary_vintage"] is None


def test_every_basin_line_carries_a_handle_that_resolves(
    client: TestClient, basin_context: psycopg.Connection
) -> None:
    """R6, the project's own hard rule: no served answer without a derivation handle.

    The rule link says which decision was taken; the handle says which run of which mart read
    which boundary file to produce this row. They are two different terms in the glossary
    because they answer two different questions, and the section serves both.
    """
    body = client.get(f"/v1/wells/{EXAMPLE_API10}").json()["data"]["basin_context"]

    sidecar = body["_lineage"]
    assert set(sidecar) == {
        "basin_name",
        "basin_class",
        "play_name",
        "play_class",
        "basin_label_filed",
        "label_class",
        "label_agrees",
        "boundary_vintage",
        "geometry_basis",
        "basin_overlap",
    }
    # One run answered the whole row, and each line addresses its own column of it.
    assert len({handle.split("#", 1)[0] for handle in sidecar.values()}) == 1
    assert {handle.split("col=", 1)[1] for handle in sidecar.values()} == set(sidecar)

    handle = sidecar["basin_name"]
    assert f"api10={EXAMPLE_API10}" in handle
    assert "col=basin_name" in handle
    chain = client.get(
        "/v1/explain", params={"h": handle, "depth": "full"}
    ).json()["data"]["chains"][0]

    assert chain["handle"] == handle
    # It resolves to a run of this mart, not merely to a well-formed string: an unregistered
    # selector profile answers 422 and would leave a naked answer wearing a ring.
    operations = [node.get("operation") for node in chain["nodes"]]
    datasets = [(node.get("output") or {}).get("dataset") for node in chain["nodes"]]
    assert "mart.refresh" in operations
    assert "marts.well_basin_context" in datasets
    assert chain["terminals"]


def test_a_basin_handle_names_a_column_the_mart_actually_has(
    client: TestClient, basin_context: psycopg.Connection
) -> None:
    """The registry is the guard: a column nobody serves is refused rather than resolved."""
    handle = client.get(f"/v1/wells/{EXAMPLE_API10}").json()["data"]["basin_context"][
        "_lineage"
    ]["basin_name"]
    invented = handle.replace("col=basin_name", "col=basin_vibes")

    answer = client.get("/v1/explain", params={"h": invented})

    assert answer.status_code == 422


def test_an_unrefreshed_mart_is_a_pipeline_state_and_not_a_null_basin(
    client: TestClient, seeded: psycopg.Connection
) -> None:
    """Without the refresh there is no row, and the response says so by omitting the block
    rather than by serving a basin of null, which would read as a fact about the well."""
    body = client.get(f"/v1/wells/{EXAMPLE_API10}").json()["data"]

    assert body["basin_context"] is None
    # And the bare label is still on the wire, because that is what it always was.
    assert body["basin"] == "williston"


def test_the_card_learns_whether_a_peer_control_exists_without_asking(
    client: TestClient,
) -> None:
    """M-4: the section is gated on a link, and the link is emitted from the held-out fact.

    A card that had to request the control to find out whether it exists would ask on every
    well and be told 404 on almost all of them; a card that guessed from a basin name would be
    writing `williston` into the client.
    """
    body = client.get(f"/v1/wells/{EXAMPLE_API10}").json()

    scope = body["data"]["type_curve_scope"]
    assert scope["published"] is True
    assert scope["held_out"] is True
    assert scope["basin"]
    assert scope["publication_id"]
    assert scope["split_set_id"]
    assert scope["detail"] is None
    assert body["links"]["type_curve"] == f"/v1/wells/{EXAMPLE_API10}/type-curve"


def test_a_well_the_control_was_fitted_on_is_offered_no_control(client: TestClient) -> None:
    """The leakage guard, served: a control fitted on this well and then compared against it
    would be measuring its own training data, so the link is absent and the scope says why."""
    body = client.get(f"/v1/wells/{TX_API10}").json()

    scope = body["data"]["type_curve_scope"]
    assert scope["held_out"] is False
    assert "type_curve" not in body["links"]
    assert scope["detail"]
    assert scope["basin"] in scope["detail"]
    assert "training data" in scope["detail"]
