"""The basin-context mart: driven off the well list, and canonical only.

Two properties carry the whole design. The row count is the well count by construction, which
is only true because the mart is driven off canonical.wells_latest and left-joined to geometry
rather than the other way round -- on the deployed spine canonical.well_spatial holds surface
points for 1,486 api10s with no row in wells_latest, 1,400 of them Montana, and a mart driven
off geometry would serve those as rows with no well behind them. And every absence carries a
class, so an unanswered basin is never a null a reader has to interpret.
"""

from __future__ import annotations

from pathlib import Path

import psycopg
import pytest

import glasswell
from glasswell.lineage.capture import lineage_session
from glasswell.lineage.store import PostgresRecorder
from glasswell.marts.well_basin_context import (
    IN_BOUNDARY,
    NO_GEOMETRY,
    refresh_well_basin_context,
)
from glasswell.seed import seed_all
from glasswell.seed.conformance_basin_context import OUTSIDE
from tests.support.layers import schema_reads_in
from tests.support.seed import (
    FIXTURE_ENV,
    seed_derivation,
    seed_manifest,
    seed_well,
    seed_well_spatial,
)

pytestmark = pytest.mark.integration

MART_SOURCE = Path(glasswell.__file__).parent / "marts" / "well_basin_context.py"

# Two rings around the fixture's surface point (47.9075, -103.5803): one containing basin and
# one containing play, so the join has something true to find; and one far away, so a well
# outside them is outside by geometry rather than by an empty table.
INSIDE_RING = "MULTIPOLYGON(((-104 47, -103 47, -103 48, -104 48, -104 47)))"
FAR_RING = "MULTIPOLYGON(((-90 30, -89 30, -89 31, -90 31, -90 30)))"
INSIDE_POINT = "POINT(-103.5803 47.9075)"
OUTSIDE_POINT = "POINT(-100.0 40.0)"


def boundary(
    connection: psycopg.Connection,
    *,
    boundary_id: str,
    kind: str,
    name: str,
    wkt: str,
    area: float,
) -> None:
    manifest = seed_manifest(connection, sha256="e" * 64, source_key="basins.zip")
    derivation = seed_derivation(connection, operation="canonical.promote")
    with connection.cursor() as cursor:
        cursor.execute(
            "insert into canonical.basin_boundaries (boundary_id, boundary_kind, name,"
            " area_sq_mi, area_basis, vintage_label, geom, source_datum, source_manifest_id,"
            " derivation_id)"
            " values (%s, %s, %s, %s, 'published', '2024',"
            " st_geomfromtext(%s, 4326), 'EPSG:4326', %s, %s)",
            (boundary_id, kind, name, area, wkt, manifest, derivation),
        )


@pytest.fixture
def spine(db: psycopg.Connection) -> psycopg.Connection:
    seed_all(db)
    boundary(
        db,
        boundary_id="eia_basin_williston",
        kind="basin",
        name="WILLISTON",
        wkt=INSIDE_RING,
        area=200000,
    )
    boundary(
        db,
        boundary_id="eia_play_bakken",
        kind="play",
        name="BAKKEN",
        wkt=INSIDE_RING,
        area=50000,
    )
    boundary(
        db, boundary_id="eia_basin_far", kind="basin", name="FAR", wkt=FAR_RING, area=1000
    )
    db.commit()
    return db


def refresh(connection: psycopg.Connection):
    with lineage_session(
        recorder=PostgresRecorder(connection), environment=FIXTURE_ENV
    ):
        result = refresh_well_basin_context(connection)
    connection.commit()
    return result


def mart_rows(connection: psycopg.Connection) -> dict[str, dict]:
    with connection.cursor() as cursor:
        cursor.execute(
            "select api10, basin_name, basin_class, play_name, play_class,"
            " basin_label_filed, label_class, label_agrees, boundary_vintage,"
            " geometry_basis, rule_id"
            " from marts.well_basin_context"
        )
        names = [column.name for column in cursor.description]
        return {row[0]: dict(zip(names, row, strict=True)) for row in cursor.fetchall()}


def test_the_mart_reads_canonical_only(spine: psycopg.Connection) -> None:
    """Blueprint §3.0.1: marts read canonical, parsers write staging, and neither crosses."""
    assert schema_reads_in(MART_SOURCE, "staging") == []
    assert schema_reads_in(MART_SOURCE, "raw") == []


def test_its_row_count_is_the_well_count_by_construction(spine: psycopg.Connection) -> None:
    """Driven off the well list, so a geometry row with no well behind it produces no row.

    This is N-3 made mechanical: on the deployed spine 1,486 api10s carry surface geometry and
    no wells_latest row, and a mart driven off well_spatial would serve every one of them.
    """
    seed_well(spine, api10="3305310451")
    seed_well_spatial(spine, api10="3305310451", geom_type="surface", wkt=INSIDE_POINT)
    # Geometry with no well behind it: exactly the shape that must produce nothing.
    seed_well_spatial(spine, api10="3305399999", geom_type="surface", wkt=INSIDE_POINT)
    spine.commit()

    result = refresh(spine)
    rows = mart_rows(spine)

    with spine.cursor() as cursor:
        cursor.execute("select count(*) from canonical.wells_latest")
        wells = int(cursor.fetchone()[0])
    assert result.rows == wells
    assert set(rows) == {"3305310451"}
    assert "3305399999" not in rows


def test_a_well_inside_a_published_basin_answers_with_it_and_its_plays(
    spine: psycopg.Connection,
) -> None:
    seed_well(spine, api10="3305310451", basin="williston")
    seed_well_spatial(spine, api10="3305310451", geom_type="surface", wkt=INSIDE_POINT)
    spine.commit()

    refresh(spine)
    row = mart_rows(spine)["3305310451"]

    assert row["basin_class"] == IN_BOUNDARY
    assert row["basin_name"] == "WILLISTON"
    assert row["play_name"] == ["BAKKEN"]
    assert row["play_class"] == "plays"
    assert row["geometry_basis"] == "surface"
    # The rule comes from the registry, so the row names the decision that produced it.
    assert row["rule_id"] == "cr_nd_basin_context_1"


def test_the_filed_label_is_kept_beside_the_polygon_and_marked(
    spine: psycopg.Connection,
) -> None:
    # The Texas case in miniature: the ingest slice says one thing and the polygon says another.
    seed_well(spine, api10="4200345818", state_code="42", basin="permian")
    seed_well_spatial(spine, api10="4200345818", geom_type="surface", wkt=INSIDE_POINT)
    seed_well(spine, api10="3305310451", basin="williston")
    seed_well_spatial(spine, api10="3305310451", geom_type="surface", wkt=INSIDE_POINT)
    spine.commit()

    refresh(spine)
    rows = mart_rows(spine)

    assert rows["4200345818"]["basin_label_filed"] == "permian"
    assert rows["4200345818"]["basin_name"] == "WILLISTON"
    assert rows["4200345818"]["label_class"] == "disagrees"
    assert rows["4200345818"]["label_agrees"] is False
    assert rows["3305310451"]["label_class"] == "agrees"
    assert rows["3305310451"]["label_agrees"] is True


def test_outside_every_boundary_and_no_geometry_are_two_different_answers(
    spine: psycopg.Connection,
) -> None:
    seed_well(spine, api10="3305300002", basin=None)
    seed_well_spatial(spine, api10="3305300002", geom_type="surface", wkt=OUTSIDE_POINT)
    seed_well(spine, api10="3305300003", basin=None)
    spine.commit()

    result = refresh(spine)
    rows = mart_rows(spine)

    assert rows["3305300002"]["basin_class"] == OUTSIDE
    assert rows["3305300002"]["basin_name"] is None
    assert rows["3305300002"]["geometry_basis"] == "surface"
    # Outside what: the boundary set that was asked, carried with its published vintage so
    # the sentence names a set rather than gesturing at one.
    assert rows["3305300002"]["boundary_vintage"] == "2024"
    assert rows["3305300003"]["boundary_vintage"] is None
    assert rows["3305300003"]["basin_class"] == NO_GEOMETRY
    assert rows["3305300003"]["geometry_basis"] == NO_GEOMETRY
    assert result.outside == 1
    assert result.no_geometry == 1


def test_the_refresh_is_a_derivation_that_names_the_rules_it_read(
    spine: psycopg.Connection,
) -> None:
    seed_well(spine, api10="3305310451", basin="williston")
    seed_well_spatial(spine, api10="3305310451", geom_type="surface", wkt=INSIDE_POINT)
    spine.commit()

    result = refresh(spine)

    with spine.cursor() as cursor:
        cursor.execute(
            "select count(*) from lineage.derivation_rules where derivation_id = %s",
            (result.derivation_id,),
        )
        rules = int(cursor.fetchone()[0])
        cursor.execute(
            "select count(*) from marts.well_basin_context where derivation_id = %s",
            (result.derivation_id,),
        )
        rows = int(cursor.fetchone()[0])
    # R8: a rule is referenced by the derivations it shaped, and these shaped every row here.
    assert rules >= 1
    assert rows == result.rows


def test_a_second_run_replaces_rather_than_appends(spine: psycopg.Connection) -> None:
    seed_well(spine, api10="3305310451", basin="williston")
    seed_well_spatial(spine, api10="3305310451", geom_type="surface", wkt=INSIDE_POINT)
    spine.commit()

    first = refresh(spine)
    second = refresh(spine)

    with spine.cursor() as cursor:
        cursor.execute("select count(*) from marts.well_basin_context")
        assert int(cursor.fetchone()[0]) == second.rows
    assert first.rows == second.rows
