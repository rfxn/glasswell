"""Montana geometry, loaded from fixtures cut out of the real MBOGC archives.

Each fixture keeps the twinned StatePlane layer the real archives ship, so layer selection is
exercised rather than assumed, and both are cut from the ND border strip so the well paths that
matter for the cross-border neighbour question are the ones under test.
"""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest

from glasswell.ingest import mt_gis
from glasswell.ingest.base import open_ingest_run
from glasswell.seed import seed_all

FIXTURES = Path(__file__).parents[1] / "fixtures" / "mt_gis"
ARCHIVES = {
    mt_gis.WELLS.source_key: FIXTURES / "Wells_sample.zip",
    mt_gis.WELL_PATHS.source_key: FIXTURES / "WellPaths_sample.zip",
}
LAYER_ROWS = 200


def client_for(path: Path) -> httpx.Client:
    payload = path.read_bytes()

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, content=payload, headers={"content-type": "application/zip"}
        )

    return httpx.Client(transport=httpx.MockTransport(handler))


@pytest.fixture
def loaded(db, raw_root, lineage_env) -> dict[str, mt_gis.LayerReport]:
    seed_all(db)
    db.commit()
    reports: dict[str, mt_gis.LayerReport] = {}
    for layer in mt_gis.LAYERS:
        with open_ingest_run(
            db, source_id=layer.source_id, raw_root=raw_root, environment=lineage_env
        ) as run, client_for(ARCHIVES[layer.source_key]) as client:
            reports[layer.source_key] = mt_gis.ingest_layer(run, layer, client=client)
    db.commit()
    return reports


def query(db, sql: str, *parameters: object) -> list[tuple]:
    with db.cursor() as cursor:
        cursor.execute(sql, parameters or None)
        return cursor.fetchall()


def scalar(db, sql: str, *parameters: object):
    return query(db, sql, *parameters)[0][0]


def test_both_layers_stage_every_record(db, loaded):
    assert scalar(db, "select count(*) from staging.mt_gis_wells") == LAYER_ROWS
    assert scalar(db, "select count(*) from staging.mt_gis_well_paths") == LAYER_ROWS


def test_the_geographic_layer_is_selected_and_not_the_stateplane_twin(db, loaded):
    """Both archives ship a _P twin; picking by sort order would be an accident of ASCII."""
    # A Montana StatePlane easting is in the hundreds of thousands; a longitude is not, and
    # ST_Transform from 32100 would have produced coordinates nowhere near Montana.
    assert scalar(
        db,
        "select count(*) from staging.mt_gis_wells"
        " where ST_X(geom) between -117 and -103 and ST_Y(geom) between 44 and 49",
    ) == LAYER_ROWS


def test_geometry_is_stored_in_4326(db, loaded):
    assert scalar(db, "select distinct ST_SRID(geom) from staging.mt_gis_wells") == 4326
    assert scalar(db, "select distinct ST_SRID(geom) from canonical.well_spatial") == 4326


def test_surface_points_and_paths_land_under_their_own_geom_type(db, loaded):
    assert query(
        db,
        "select geom_type, count(*) from canonical.well_spatial group by 1 order by 1",
    ) == [("lateral", LAYER_ROWS), ("surface", LAYER_ROWS)]


def test_every_promoted_geometry_carries_a_montana_api10(db, loaded):
    assert scalar(
        db, "select count(*) from canonical.well_spatial where api10 !~ '^25[0-9]{8}$'"
    ) == 0


def test_a_multi_path_well_keeps_every_lateral_under_its_own_wellsub_key(db, loaded):
    """cr_mt_paths_subkey_1: API-10 alone is not unique for geometry."""
    multi = query(
        db,
        "select api10, count(*) from canonical.well_spatial"
        " where geom_type = 'lateral' group by 1 having count(*) > 1 order by 1",
    )
    assert multi, "the fixture is cut to contain wells with more than one path"
    keys = scalar(
        db,
        "select count(distinct geom_key) from canonical.well_spatial"
        " where geom_type = 'lateral' and api10 = %s",
        multi[0][0],
    )
    assert keys == multi[0][1]
    assert scalar(
        db,
        "select count(*) from canonical.well_spatial where geom_type = 'lateral'"
        "   and geom_key !~ '^(LT|ST|WL)[0-9]{2}$'",
    ) == 0


def test_the_source_datum_and_transform_rule_travel_with_every_geometry(db, loaded):
    assert query(
        db, "select distinct source_datum from canonical.well_spatial"
    ) == [("EPSG:4269",)]
    assert sorted(
        row[0] for row in query(db, "select distinct transform_rule_id from canonical.well_spatial")
    ) == ["cr_mt_gis_datum_1", "cr_mt_paths_datum_1"]


def test_the_promotion_records_that_a_path_is_not_a_directional_survey(db, loaded):
    """cr_mt_paths_geometry_class_1, carried on the derivation rather than only in prose."""
    assert query(
        db,
        "select distinct params ->> 'is_directional_survey'"
        "  from lineage.derivations where operation = 'canonical.promote'"
        "   and params ->> 'geom_type' = 'lateral'",
    ) == [("false",)]


def test_an_unpromoted_status_never_becomes_a_well_header(db, loaded):
    """A water well is not an oil and gas well, and Completed is a milestone, not a state."""
    promoted = scalar(db, "select count(*) from canonical.wells")
    assert promoted < LAYER_ROWS, "the fixture must contain at least one unpromoted status"
    assert scalar(
        db,
        "select count(*) from canonical.wells where status_canonical is null",
    ) == 0
    assert loaded[mt_gis.WELLS.source_key].quarantined.get("unknown_status", 0) == (
        LAYER_ROWS - promoted
    )


def test_promoted_headers_carry_the_montana_state_code_and_reported_status(db, loaded):
    assert query(db, "select distinct state_code from canonical.wells") == [("25",)]
    assert scalar(
        db, "select count(*) from canonical.wells where status_reported is null"
    ) == 0
    assert scalar(
        db,
        "select count(*) from canonical.wells"
        " where status_canonical not in ('active', 'plugged', 'inactive', 'expired',"
        "                                'permitted', 'drilling', 'temporarily_abandoned')",
    ) == 0


def test_no_montana_well_is_given_a_basin(db, loaded):
    """cr_mt_basin_scope_1: Bakken is 4.6 percent of the state, so williston is not a default."""
    assert scalar(db, "select count(*) from canonical.wells where basin is not null") == 0


def test_a_second_load_over_the_same_bytes_adds_nothing(db, raw_root, lineage_env, loaded):
    before = scalar(db, "select count(*) from canonical.well_spatial")
    for layer in mt_gis.LAYERS:
        with open_ingest_run(
            db, source_id=layer.source_id, raw_root=raw_root, environment=lineage_env
        ) as run, client_for(ARCHIVES[layer.source_key]) as client:
            mt_gis.ingest_layer(run, layer, client=client)
    db.commit()

    assert scalar(db, "select count(*) from canonical.well_spatial") == before
    assert scalar(db, "select count(*) from staging.mt_gis_wells") == LAYER_ROWS
