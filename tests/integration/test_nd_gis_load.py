from __future__ import annotations

from pathlib import Path

import httpx
import psycopg
import pytest

from glasswell.ingest.nd_gis import (
    LAYERS,
    load_laterals,
    load_spacing_units,
    load_wells,
)
from glasswell.lineage.capture import lineage_session
from glasswell.lineage.store import PostgresRecorder
from glasswell.seed import seed_all

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "nd_gis"
ARCHIVES = {
    "wells": FIXTURES / "OGD_Wells_300.zip",
    "laterals": FIXTURES / "OGD_Horizontals_Line_300.zip",
    "spacing_units": FIXTURES / "OGD_DrillingSpacingUnits_300.zip",
}
LOADERS = {"wells": load_wells, "laterals": load_laterals, "spacing_units": load_spacing_units}

LATERAL_SEGMENTS = 233
LATERAL_WELLS = 180
MULTI_LATERAL_WELLS = 42
NON_LATERAL_SEGMENTS = 65
UNSTORABLE_GEOMETRIES = 2
WELL_RECORDS = 300
SPACING_UNITS = 300


def client_for(archive: Path) -> httpx.Client:
    payload = archive.read_bytes()

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=payload, headers={"content-type": "application/zip"})

    return httpx.Client(transport=httpx.MockTransport(handler))


def load(db, raw_root: Path, lineage_env, layer: str):
    with lineage_session(recorder=PostgresRecorder(db), environment=lineage_env), client_for(
        ARCHIVES[layer]
    ) as client:
        result = LOADERS[layer](db, raw_root=raw_root, client=client)
    db.commit()
    return result


def scalar(db, sql: str, parameters: tuple = ()):
    with db.cursor() as cursor:
        cursor.execute(sql, parameters)
        row = cursor.fetchone()
    return row[0] if row else None


def rows(db, sql: str, parameters: tuple = ()) -> list[tuple]:
    with db.cursor() as cursor:
        cursor.execute(sql, parameters)
        return cursor.fetchall()


@pytest.fixture
def seeded(db: psycopg.Connection) -> psycopg.Connection:
    """fetch_raw needs the source rows, and every promotion needs the seeded rules."""
    seed_all(db)
    db.commit()
    return db


@pytest.fixture
def wells_loaded(seeded, raw_root, lineage_env):
    return load(seeded, raw_root, lineage_env, "wells")


def test_every_layer_registers_one_manifest_and_two_derivations(seeded, raw_root, lineage_env):
    for layer in ("wells", "laterals", "spacing_units"):
        result = load(seeded, raw_root, lineage_env, layer)
        source_id = LAYERS[layer].source_id
        assert scalar(
            seeded, "select count(*) from lineage.manifests where source_id = %s", (source_id,)
        ) == 1
        assert result.manifest_id.startswith("man_")
        for operation in ("stage.parse", "canonical.promote"):
            assert scalar(
                seeded,
                "select count(*) from lineage.derivations where operation = %s"
                " and output_dataset like %s",
                (operation, f"%{LAYERS[layer].staging_table.split('.')[-1]}%")
                if operation == "stage.parse"
                else (operation, f"%{LAYERS[layer].canonical_table.split('.')[-1]}%"),
            ) == 1
        assert scalar(
            seeded, "select count(*) from lineage.vintages where source_id = %s", (source_id,)
        ) == 1


def test_the_promotion_derivation_reads_the_parse_derivation_and_the_manifest(
    seeded, raw_root, lineage_env
):
    result = load(seeded, raw_root, lineage_env, "wells")
    kinds = rows(
        seeded,
        "select kind, ref_id from lineage.derivation_inputs where derivation_id = %s order by ord",
        (result.promote_derivation_id,),
    )
    assert ("derivation", result.parse_derivation_id) in kinds
    assert ("manifest", result.manifest_id) in kinds


def test_wells_land_in_canonical_with_a_surface_geometry(wells_loaded, seeded):
    assert wells_loaded.promoted_rows == WELL_RECORDS
    assert scalar(seeded, "select count(*) from canonical.wells") == WELL_RECORDS
    assert (
        scalar(seeded, "select count(*) from canonical.well_spatial where geom_type = 'surface'")
        == WELL_RECORDS
    )
    assert scalar(
        seeded, "select count(distinct geom_key) from canonical.well_spatial"
        " where geom_type = 'surface'"
    ) == 1
    assert scalar(
        seeded, "select geom_key from canonical.well_spatial where geom_type = 'surface' limit 1"
    ) == "surface"
    assert scalar(
        seeded,
        "select api14 from canonical.wells where api10 = %s",
        ("3304300002",),
    ) == "33043000020000"
    assert scalar(
        seeded, "select spud_date::text from canonical.wells where api10 = %s", ("3304300002",)
    ) == "1928-05-27"
    assert scalar(
        seeded, "select land_unit_label from canonical.wells where api10 = %s", ("3304300002",)
    ) == "140N-73W-2"


def test_well_status_is_mapped_through_the_seeded_vocabulary(wells_loaded, seeded):
    assert scalar(
        seeded, "select status_canonical from canonical.wells where status_reported = 'DRY' limit 1"
    ) == "dry"
    assert scalar(
        seeded, "select count(*) from canonical.wells where status_canonical is null"
    ) == 0
    confidential = rows(
        seeded,
        "select status_reported, status_canonical, confidential_flag from canonical.wells"
        " where confidential_flag",
    )
    assert confidential
    assert {row[0] for row in confidential} == {"Confidential"}
    assert {row[1] for row in confidential} == {"confidential"}
    assert scalar(
        seeded, "select count(*) from canonical.wells where confidential_flag"
    ) == scalar(
        seeded, "select count(*) from canonical.wells where status_reported = 'Confidential'"
    )


def test_every_geometry_row_is_4326_with_a_recorded_datum_and_transform_rule(
    wells_loaded, seeded, raw_root, lineage_env
):
    load(seeded, raw_root, lineage_env, "laterals")
    assert scalar(
        seeded, "select count(*) from canonical.well_spatial where ST_SRID(geom) <> 4326"
    ) == 0
    assert scalar(
        seeded, "select count(*) from canonical.well_spatial where source_datum <> 'EPSG:4269'"
    ) == 0
    assert scalar(
        seeded,
        "select count(*) from canonical.well_spatial where transform_rule_id is distinct from %s",
        ("cr_nd_datum_1",),
    ) == 0
    assert scalar(seeded, "select count(*) from canonical.spacing_units") == 0


def test_laterals_are_keyed_by_linekey_and_only_lateral_segments_are_promoted(
    wells_loaded, seeded, raw_root, lineage_env
):
    result = load(seeded, raw_root, lineage_env, "laterals")
    assert result.promoted_rows == LATERAL_SEGMENTS
    assert scalar(
        seeded, "select count(*) from canonical.well_spatial where geom_type = 'lateral'"
    ) == LATERAL_SEGMENTS
    assert scalar(
        seeded,
        "select count(*) from canonical.well_spatial where geom_type = 'lateral'"
        " and geom_key not like %s",
        ("%\\_LAT%",),
    ) == 0
    assert scalar(
        seeded,
        "select count(*) from canonical.well_spatial where geom_type = 'lateral'"
        " and ST_GeometryType(geom) <> 'ST_LineString'",
    ) == 0
    assert result.quarantined["unknown_vocab"] == NON_LATERAL_SEGMENTS
    # Two _VERT records are disjoint multi-part lines: staging.geom is geometry(LineString),
    # so they stage without geometry and are measured rather than dropped.
    assert result.quarantined["parse_error"] == UNSTORABLE_GEOMETRIES
    assert scalar(
        seeded,
        "select count(*) from lineage.quarantine_rows where reason_code = 'parse_error'"
        " and row_payload ->> 'detail' like %s",
        ("MultiLineString%",),
    ) == UNSTORABLE_GEOMETRIES


def test_a_multi_lateral_well_keeps_every_centreline_and_raises_one_quarantine_row(
    wells_loaded, seeded, raw_root, lineage_env
):
    result = load(seeded, raw_root, lineage_env, "laterals")
    keys = [
        row[0]
        for row in rows(
            seeded,
            "select geom_key from canonical.well_spatial where api10 = %s and geom_type = 'lateral'"
            " order by geom_key",
            ("3301100391",),
        )
    ]
    assert keys == ["33011003910000_LAT1", "33011003910000_LAT2"]

    measured = rows(
        seeded,
        "select row_payload ->> 'api10', row_payload ->> 'lateral_count', rule_id, stage"
        " from lineage.quarantine_rows where reason_code = 'multi_wellbore_policy'"
        " and row_payload ->> 'api10' = %s",
        ("3301100391",),
    )
    assert measured == [("3301100391", "2", "cr_nd_multilateral_1", "validate")]
    assert result.quarantined["multi_wellbore_policy"] == MULTI_LATERAL_WELLS
    assert scalar(
        seeded,
        "select count(*) from lineage.quarantine_rows where reason_code = 'multi_wellbore_policy'",
    ) == MULTI_LATERAL_WELLS
    assert result.multi_lateral_rate == pytest.approx(MULTI_LATERAL_WELLS / LATERAL_WELLS)


def test_lateral_length_comes_from_the_geodesic_measure_and_not_from_shape_leng(
    wells_loaded, seeded, raw_root, lineage_env
):
    result = load(seeded, raw_root, lineage_env, "laterals")
    measured = rows(
        seeded,
        "select s.geom_key,"
        "       ST_Length(s.geom::geography) / 0.3048 as feet,"
        "       g.shape_leng::double precision"
        "  from canonical.well_spatial s"
        "  join staging.nd_gis_laterals g on g.linekey = s.geom_key"
        " where s.geom_type = 'lateral'",
    )
    assert len(measured) == LATERAL_SEGMENTS
    feet = sorted(row[1] for row in measured)
    median = feet[len(feet) // 2]
    assert 500 <= median <= 25000
    # SHAPE_Leng is degrees: the measured length is five orders of magnitude larger.
    for _, computed, shape_leng in measured:
        assert shape_leng < 1
        assert computed / shape_leng > 10_000

    assert result.length_stats["median_ft"] == pytest.approx(median, rel=1e-6)
    assert 500 <= result.length_stats["median_ft"] <= 25000


def test_a_lateral_without_a_well_row_quarantines_instead_of_failing_the_batch(
    seeded, raw_root, lineage_env
):
    result = load(seeded, raw_root, lineage_env, "laterals")

    assert result.promoted_rows == 0
    assert scalar(seeded, "select count(*) from canonical.well_spatial") == 0
    assert result.quarantined["orphan_fk"] == LATERAL_SEGMENTS
    assert scalar(
        seeded,
        "select count(*) from lineage.quarantine_rows where reason_code = 'orphan_fk'"
        " and stage = 'join'",
    ) == LATERAL_SEGMENTS
    assert scalar(seeded, "select count(*) from staging.nd_gis_laterals") == 300


def test_spacing_units_load_with_multipolygon_geometry(seeded, raw_root, lineage_env):
    result = load(seeded, raw_root, lineage_env, "spacing_units")

    assert result.promoted_rows == SPACING_UNITS
    assert scalar(seeded, "select count(*) from canonical.spacing_units") == SPACING_UNITS
    assert scalar(
        seeded,
        "select count(*) from canonical.spacing_units"
        " where ST_GeometryType(geom) <> 'ST_MultiPolygon' or ST_SRID(geom) <> 4326",
    ) == 0
    assert scalar(
        seeded, "select count(distinct spacing_unit_id) from canonical.spacing_units"
    ) == SPACING_UNITS
    label, acres, state = rows(
        seeded,
        "select label, ds_size_acres, state from canonical.spacing_units order by spacing_unit_id"
        " limit 1",
    )[0]
    assert label == "1280SPC"
    assert float(acres) == 1280.0
    assert state == "ND"


def test_staging_keeps_every_source_row_including_the_segments_not_promoted(
    wells_loaded, seeded, raw_root, lineage_env
):
    load(seeded, raw_root, lineage_env, "laterals")
    assert scalar(seeded, "select count(*) from staging.nd_gis_laterals") == 300
    assert scalar(seeded, "select count(*) from staging.nd_gis_wells") == WELL_RECORDS
    assert scalar(
        seeded, "select count(*) from staging.nd_gis_laterals where linekey like %s", ("%\\_VERT",)
    ) == 40
    assert scalar(
        seeded, "select count(*) from staging.nd_gis_laterals where ST_SRID(geom) <> 4326"
    ) == 0


def test_reloading_the_identical_file_is_a_no_op(seeded, raw_root, lineage_env):
    first = load(seeded, raw_root, lineage_env, "wells")
    before = scalar(seeded, "select count(*) from lineage.derivations")

    second = load(seeded, raw_root, lineage_env, "wells")

    assert second.unchanged is True
    assert second.manifest_id == first.manifest_id
    assert second.promoted_rows == 0
    assert scalar(seeded, "select count(*) from lineage.manifests") == 1
    assert scalar(seeded, "select count(*) from canonical.wells") == WELL_RECORDS
    assert scalar(seeded, "select count(*) from staging.nd_gis_wells") == WELL_RECORDS
    # raw.fetch is content-addressed, so the repeat fetch reconciles onto the same row.
    assert scalar(seeded, "select count(*) from lineage.derivations") == before


def test_the_compute_crs_directive_is_read_from_the_registry_not_hard_coded(
    wells_loaded, seeded, raw_root, lineage_env
):
    result = load(seeded, raw_root, lineage_env, "laterals")
    # A3-F1: the active rule measures geodesically, so no zone is pinned anywhere in code.
    assert (result.length_rule_id, result.compute_epsg) == ("cr_nd_compute_crs_2", None)
    applied = [
        row[0]
        for row in rows(
            seeded,
            "select rule_id from lineage.derivation_rules where derivation_id = %s"
            " order by rule_id",
            (result.promote_derivation_id,),
        )
    ]
    assert applied == ["cr_nd_compute_crs_2", "cr_nd_datum_1", "cr_nd_multilateral_1"]
