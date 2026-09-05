"""The Montana tile marts: a point layer and a path layer.

Modelled on `test_marts_nm.py`. What is specific to Montana is what the path layer must carry
and what neither layer may: the map-stick class and the vertex count ride on every path feature
(cr_mt_paths_geometry_class_1), no figure anywhere claims a length, and `basin` stays absent
because cr_mt_basin_scope_1 leaves the state untagged.
"""

from __future__ import annotations

from datetime import date

import psycopg
import pytest

from glasswell.api.routers.tiles import PUBLISHED_LAYERS
from glasswell.ingest.base import resolve_environment
from glasswell.lineage.capture import lineage_session
from glasswell.lineage.store import PostgresRecorder
from glasswell.marts import mt_wells as mt_marts
from glasswell.marts.wells import profile_for, refresh_for
from glasswell.seed import seed_all
from tests.integration.test_marts_nd import covering_tile, extent_of, rows, scalar
from tests.support.jurisdictions import declared_rule
from tests.support.mvt import attribute_keys, feature_count, layer_name, layers
from tests.support.seed import seed_manifest, seed_well, seed_well_spatial

pytestmark = pytest.mark.integration

MT_API10S = ("2508321001", "2508321002")
MT_SURFACE = ("POINT(-104.6000 47.8000)", "POINT(-104.5000 47.9000)")
# A Montana point whose api10 carries no header row. Not an edge case here: the six MBOGC
# statuses cr_mt_gis_status_vocab_1 does not promote quarantine, so 1,400 real points are
# exactly this shape and must still tile.
MT_ORPHAN = "2508321003"
MT_ORPHAN_SURFACE = "POINT(-104.4000 48.0000)"
# One well carrying two paths, which is the 875-well case cr_mt_paths_subkey_1 exists for.
MT_PATHS = (
    (MT_API10S[0], "LT01", "LINESTRING(-104.6000 47.8000, -104.5800 47.8100)"),
    (MT_API10S[0], "LT02", "LINESTRING(-104.6000 47.8000, -104.5900 47.7900)"),
    (MT_API10S[1], "WL01", "LINESTRING(-104.5000 47.9000, -104.4900 47.9050, -104.4850 47.9070)"),
)
ND_API10 = "3305399001"
ND_SURFACE = "POINT(-102.7850 47.9400)"

WELL_TILE_KEYS = {
    "api10", "operator_name", "status_canonical", "status_reported", "well_type_reported",
    "completion_year", "derivation_id",
}
PATH_TILE_KEYS = {
    "api10", "geom_key", "operator_name", "status_canonical", "geometry_class", "vertex_count",
    "derivation_id",
}


@pytest.fixture
def refreshed(db: psycopg.Connection, lineage_env):
    seed_all(db)
    manifest = seed_manifest(db, sha256="c" * 64, source_id="mt_gis_wells")
    for api10, surface in zip(MT_API10S, MT_SURFACE, strict=True):
        seed_well(
            db,
            api10=api10,
            state_code="25",
            manifest_id=manifest,
            status_canonical="plugged",
            status_reported="P&A - Approved",
            well_type_reported="Dry Hole",
            operator_name_reported="CONTINENTAL RESOURCES INC",
            completion_date=date(2011, 7, 14),
            spud_date=None,
            basin=None,
        )
        seed_well_spatial(
            db,
            api10=api10,
            geom_type="surface",
            wkt=surface,
            manifest_id=manifest,
            transform_rule_id="cr_mt_gis_datum_1",
        )
    seed_well_spatial(
        db,
        api10=MT_ORPHAN,
        geom_type="surface",
        wkt=MT_ORPHAN_SURFACE,
        manifest_id=manifest,
        transform_rule_id="cr_mt_gis_datum_1",
    )
    for api10, wellsub, wkt in MT_PATHS:
        seed_well_spatial(
            db,
            api10=api10,
            geom_type="lateral",
            geom_key=wellsub,
            wkt=wkt,
            manifest_id=manifest,
            transform_rule_id="cr_mt_paths_datum_1",
        )
    seed_well(db, api10=ND_API10)
    seed_well_spatial(db, api10=ND_API10, geom_type="surface", wkt=ND_SURFACE)
    seed_well_spatial(db, api10=ND_API10, geom_type="lateral")
    db.commit()

    with lineage_session(recorder=PostgresRecorder(db), environment=lineage_env):
        refresh = refresh_for(db, "MT")
    db.commit()
    return db, refresh


def test_the_refresh_publishes_both_layers_and_rebuilds_rather_than_appends(refreshed):
    db, refresh = refreshed

    assert refresh.layers == ("mt_wells", "mt_paths")
    assert refresh.row_counts == {
        "mt_wells_tile": len(MT_API10S) + 1,
        "mt_paths_tile": len(MT_PATHS),
    }
    with lineage_session(
        recorder=PostgresRecorder(db),
        environment=resolve_environment(db, env_id="env_mt_repeat"),
    ):
        again = refresh_for(db, "MT")
    db.commit()
    assert again.row_counts == refresh.row_counts
    for table in ("mt_wells_tile", "mt_paths_tile"):
        assert scalar(db, f"select count(distinct derivation_id) from marts.{table}") == 1


def test_a_multi_path_well_keeps_every_path_rather_than_one(refreshed):
    """cr_mt_paths_subkey_1: keyed on API-10 alone, two of these three rows would be lost."""
    db, _ = refreshed

    assert rows(
        db,
        "select geom_key from marts.mt_paths_tile where api10 = %s order by geom_key",
        (MT_API10S[0],),
    ) == [("LT01",), ("LT02",)]


def test_every_path_states_its_class_and_its_vertex_count_on_the_feature(refreshed):
    """cr_mt_paths_geometry_class_1 requires the map-stick distinction wherever the geometry is
    served, so it is a property of the feature and not a caveat somewhere else."""
    db, _ = refreshed

    assert rows(
        db,
        "select geometry_class, vertex_count from marts.mt_paths_tile"
        " where api10 = %s order by geom_key",
        (MT_API10S[1],),
    ) == [("map_stick", 3)]
    assert rows(db, "select distinct geometry_class from marts.mt_paths_tile") == [("map_stick",)]


def test_nothing_the_montana_marts_publish_claims_a_length(refreshed):
    """Montana carries no basin (cr_mt_basin_scope_1) and `lengths` is keyed by basin, so there
    is no registered method to measure one with. A length here would be a naked number."""
    db, _ = refreshed
    columns = {
        name
        for (name,) in rows(
            db,
            "select column_name from information_schema.columns"
            " where table_schema = 'marts' and table_name in"
            "       ('mt_wells_tile', 'mt_paths_tile')",
        )
    }

    assert not any("length" in name for name in columns)
    assert "length" not in _montana_sql().lower()
    # The invariant behind the columns, stated where it now lives: Montana registers a serving
    # length_scope rule, which the engine reads as `withheld` and refuses to publish under.
    assert declared_rule("25", "length_scope") is not None
    assert not profile_for("MT").serves_a_length


def test_a_geometry_with_no_well_row_still_tiles_unstyled(refreshed):
    db, _ = refreshed

    assert rows(
        db,
        "select operator_name, status_canonical, completion_year from marts.mt_wells_tile"
        " where api10 = %s",
        (MT_ORPHAN,),
    ) == [(None, None, None)]


def test_the_point_layer_carries_a_completion_year_and_never_a_spud_one(refreshed):
    """MBOGC files Completed and no spud date; a spud_year column here would be empty by
    construction and read as a missing fact rather than an absent one."""
    db, _ = refreshed
    columns = {
        name
        for (name,) in rows(
            db,
            "select column_name from information_schema.columns"
            " where table_schema = 'marts' and table_name = 'mt_wells_tile'",
        )
    }

    assert "spud_year" not in columns
    assert scalar(
        db, "select completion_year from marts.mt_wells_tile where api10 = %s", (MT_API10S[0],)
    ) == 2011


def test_no_other_states_geometry_is_in_the_montana_marts(refreshed):
    db, _ = refreshed

    assert rows(db, "select distinct left(api10, 2) from marts.mt_wells_tile") == [("25",)]
    assert rows(db, "select distinct left(api10, 2) from marts.mt_paths_tile") == [("25",)]


def test_the_nd_mart_does_not_sweep_the_montana_paths_in(refreshed, lineage_env):
    """The sibling half: Montana promotes its paths as `lateral` geometry, which is the class
    the ND laterals mart selects on, so the state filter is the only thing separating them."""
    db, _ = refreshed
    with lineage_session(recorder=PostgresRecorder(db), environment=lineage_env):
        refresh_for(db, "ND")
    db.commit()

    assert rows(db, "select distinct left(api10, 2) from marts.nd_laterals_tile") == [("33",)]
    assert rows(db, "select distinct left(api10, 2) from marts.nd_wells_tile") == [("33",)]


def test_the_derivation_records_the_state_the_absent_basin_and_the_rules_it_cited(refreshed):
    db, refresh = refreshed
    params = scalar(
        db,
        "select params from lineage.derivations where derivation_id = %s",
        (refresh.derivation_id,),
    )
    cited = {
        rule
        for (rule,) in rows(
            db,
            "select rule_id from lineage.derivation_rules where derivation_id = %s",
            (refresh.derivation_id,),
        )
    }

    assert params["state_code"] == "25"
    assert params["basin"] is None
    assert params["length_served"] is False
    assert params["geometry_class"] == "map_stick"
    assert params["layers"] == ["mt_wells", "mt_paths"]
    assert {
        "cr_mt_basin_scope_1",
        "cr_mt_gis_datum_1",
        "cr_mt_paths_datum_1",
        "cr_mt_paths_geometry_class_1",
        "cr_mt_paths_coverage_1",
        "cr_mt_paths_subkey_1",
        "cr_mt_gis_status_vocab_1",
    } <= cited


def test_no_montana_well_is_given_a_basin_by_the_serving_path(refreshed):
    """The peer-ladder guard: `williston` reaching a Madison well is the failure
    cr_mt_basin_scope_1 exists to prevent, and serving is the last place it could enter."""
    db, _ = refreshed

    assert scalar(
        db, "select count(*) from canonical.wells where state_code = '25' and basin is not null"
    ) == 0


def test_both_montana_layers_are_published_and_no_third_one_is(refreshed):
    assert {"mt_wells", "mt_paths"} <= PUBLISHED_LAYERS
    assert "mt_laterals" not in PUBLISHED_LAYERS
    assert {name for name in PUBLISHED_LAYERS if name.startswith("mt_")} == {
        "mt_wells", "mt_paths"
    }


def test_both_layers_serve_a_decodable_tile_with_their_declared_properties(refreshed):
    db, _ = refreshed
    for table, function, expected, keys in (
        ("mt_wells_tile", "mt_wells", len(MT_API10S) + 1, WELL_TILE_KEYS),
        ("mt_paths_tile", "mt_paths", len(MT_PATHS), PATH_TILE_KEYS),
    ):
        zoom, x, y = covering_tile(extent_of(db, f"marts.{table}"))
        body = scalar(db, f"select marts.{function}(%s, %s, %s)", (zoom, x, y))

        assert body, function
        decoded = layers(bytes(body))
        assert layer_name(decoded[0]) == function
        assert feature_count(decoded[0]) == expected
        assert set(attribute_keys(decoded[0])) <= keys


def test_the_map_stick_class_survives_the_trip_through_the_tile(refreshed):
    """A property the mart holds and the tile drops would leave the served geometry unlabelled,
    which is the exact thing cr_mt_paths_geometry_class_1 forbids."""
    db, _ = refreshed
    zoom, x, y = covering_tile(extent_of(db, "marts.mt_paths_tile"))
    body = scalar(db, "select marts.mt_paths(%s, %s, %s)", (zoom, x, y))
    decoded = layers(bytes(body))

    assert {"geometry_class", "vertex_count"} <= set(attribute_keys(decoded[0]))


def _montana_sql() -> str:
    """Every statement Montana's refresh runs, composed from the profile the engine reads."""
    profile = profile_for(mt_marts.JURISDICTION_CODE)
    return "".join(projection.select for projection in profile.projections)
