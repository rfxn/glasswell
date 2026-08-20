"""A5-F8: a multi-part centreline parsed fine — the staging column could not hold it.

583 rows were labelled `parse_error` under a detail that said, in the row's own payload, that
the geometry type did not fit the column. Six of them are laterals, so six real centrelines
were dropped from canonical under a code that says the file was unreadable.
"""

from __future__ import annotations

import psycopg
from psycopg.types.json import Jsonb

from glasswell.seed import seed_all
from tests.integration.test_lateral_length_truth import laterals_loaded  # noqa: F401
from tests.integration.test_marts_nd import rows, scalar
from tests.integration.test_migration_014 import migration_sql
from tests.support.seed import seed_manifest

GIS_SOURCE = "nd_gis_horizontals_line"
FIXTURE_MULTIPART = ("33025003920000_VERT", "33007011950000_VERT")


def test_a_multi_part_record_reaches_staging_with_its_geometry(laterals_loaded):  # noqa: F811
    staged = rows(
        laterals_loaded,
        "select linekey, ST_GeometryType(geom), ST_NumGeometries(geom)"
        "  from staging.nd_gis_laterals where linekey = any(%s) order by linekey",
        (list(FIXTURE_MULTIPART),),
    )

    assert [(key, kind) for key, kind, _ in staged] == [
        (FIXTURE_MULTIPART[1], "ST_MultiLineString"),
        (FIXTURE_MULTIPART[0], "ST_MultiLineString"),
    ]
    assert all(parts > 1 for _, _, parts in staged)


def test_nothing_stages_without_geometry_any_more(laterals_loaded):  # noqa: F811
    assert scalar(laterals_loaded, "select count(*) from staging.nd_gis_laterals"
                                   " where geom is null") == 0


def test_the_layer_raises_no_parse_error_for_a_shape_it_parsed(laterals_loaded):  # noqa: F811
    labels = rows(
        laterals_loaded,
        "select reason_code, count(*) from lineage.quarantine_rows where source_id = %s"
        " group by 1 order by 1",
        (GIS_SOURCE,),
    )

    assert "parse_error" not in {reason for reason, _ in labels}


def test_no_row_from_the_gis_load_is_left_without_a_rule(laterals_loaded):  # noqa: F811
    """C17/U12: every quarantine row links to the conformance rule that rejected it."""
    unruled = scalar(
        laterals_loaded,
        "select count(*) from lineage.quarantine_rows where source_id = %s and rule_id is null",
        (GIS_SOURCE,),
    )

    assert unruled == 0


def test_a_multi_part_lateral_promotes_and_is_measured(laterals_loaded):  # noqa: F811
    """Six production laterals are multi-part; ST_Length over the parts is their length."""
    with laterals_loaded.cursor() as cursor:
        cursor.execute(
            "insert into canonical.well_spatial (api10, geom_type, geom_key, geom, source_datum,"
            " transform_rule_id, source_manifest_id, derivation_id)"
            " select api10, 'lateral', '33011010580000_LAT1',"
            "        ST_GeomFromText('MULTILINESTRING((-103.58 47.90, -103.55 47.90),"
            "                                         (-103.54 47.90, -103.52 47.90))', 4326),"
            "        source_datum, transform_rule_id, source_manifest_id, derivation_id"
            "   from canonical.well_spatial where geom_type = 'lateral' limit 1"
        )
        cursor.execute(
            "select ST_GeometryType(geom), ST_Length(geom::geography) / 0.3048"
            "  from canonical.well_spatial where geom_key = '33011010580000_LAT1'"
        )
        kind, feet = cursor.fetchone()

    assert kind == "ST_MultiLineString"
    assert 10_000 < feet < 20_000


def test_the_migration_relabels_the_ledger_from_the_detail_it_stored(
    db: psycopg.Connection,
) -> None:
    """The VM's 583 rows, bounded by the payload field that already stated the true cause."""
    seed_all(db)
    manifest = seed_manifest(db, sha256="c" * 64, source_id=GIS_SOURCE, source_key="OGD.zip")
    payloads = [
        ("qtn_mls_1", {"linekey": "33013013270000_VERT",
                       "detail": "MultiLineString does not fit the declared LineString column"}),
        ("qtn_mls_2", {"linekey": "33011010580000_LAT1",
                       "detail": "MultiLineString does not fit the declared LineString column"}),
        ("qtn_empty", {"linekey": "33011010590000_LAT1",
                       "detail": "the source record carries no geometry"}),
    ]
    with db.cursor() as cursor:
        for quarantine_id, payload in payloads:
            cursor.execute(
                "insert into lineage.quarantine_rows (quarantine_id, row_fingerprint, source_id,"
                " staging_table, stage, reason_code, row_payload, first_seen_at,"
                " first_seen_manifest_id, last_seen_at, last_seen_manifest_id)"
                " values (%s, %s, %s, 'staging.nd_gis_laterals', 'parse', 'parse_error',"
                " %s, now(), %s, now(), %s)",
                (quarantine_id, quarantine_id, GIS_SOURCE, Jsonb(payload), manifest, manifest),
            )
        cursor.execute(migration_sql("multipart_geometry"))
        cursor.execute(
            "select quarantine_id, reason_code, state, notes is not null"
            "  from lineage.quarantine_rows order by quarantine_id"
        )
        relabelled = cursor.fetchall()
        cursor.execute(
            "select payload from lineage.audit_events"
            " where event_id = 'evt_migration_017_schema_mismatch'"
        )
        event = cursor.fetchone()

    assert relabelled == [
        ("qtn_empty", "parse_error", "open", False),
        ("qtn_mls_1", "schema_mismatch", "superseded", True),
        ("qtn_mls_2", "schema_mismatch", "superseded", True),
    ]
    assert event is not None
    assert event[0]["rows"] == 2
    assert event[0]["finding"] == "fp-audit A5-F8"
