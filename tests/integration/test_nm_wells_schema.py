"""What the canonical spine already admits for New Mexico, and the two refusals it did not.

`canonical.wells` and `canonical.well_spatial` carry no state constraint and `geom_type` already
admits `surface`, so prefix 30 needs no widening. That is a claim about the schema rather than
about a plan, so it is asserted here — and the assertion is deliberately kept even though it
passes trivially today: it is a regression guard against a future state check, and deleting a
guard because it currently passes trivially is how the constraint gets added later.
"""

from __future__ import annotations

from datetime import date

import psycopg
import pytest
from psycopg.types.json import Jsonb

from glasswell.seed import seed_all
from tests.support.seed import seed_derivation, seed_manifest

pytestmark = pytest.mark.integration

NM_API10 = "3001512345"
NM_POINT = "POINT(-103.9 32.1)"


@pytest.fixture
def anchors(db: psycopg.Connection, lineage_env) -> tuple[str, str]:
    # The quarantine row's FKs run to lineage.sources and lineage.conformance_rules, so the
    # registry has to be resident before a refusal can be filed against its own rule.
    seed_all(db)
    manifest = seed_manifest(db, sha256="a" * 64, source_id="nm_ocd_wcproduction")
    return manifest, seed_derivation(db)


def insert_well(db: psycopg.Connection, anchors: tuple[str, str], **overrides) -> None:
    manifest, derivation = anchors
    values = {
        "api10": NM_API10,
        "state_code": "30",
        "status_reported": "A",
        "status_canonical": None,
        "well_type_reported": "O",
        "effective_from": date(2019, 4, 1),
        **overrides,
    }
    with db.cursor() as cursor:
        cursor.execute(
            "insert into canonical.wells (api10, state_code, status_reported, status_canonical,"
            " well_type_reported, effective_from, source_manifest_id, derivation_id)"
            " values (%(api10)s, %(state_code)s, %(status_reported)s, %(status_canonical)s,"
            " %(well_type_reported)s, %(effective_from)s, %(manifest)s, %(derivation)s)",
            {**values, "manifest": manifest, "derivation": derivation},
        )


def insert_spatial(db: psycopg.Connection, anchors: tuple[str, str], **overrides) -> None:
    manifest, derivation = anchors
    values = {
        "api10": NM_API10,
        "geom_type": "surface",
        "geom_key": "surface",
        "wkt": NM_POINT,
        "source_datum": "EPSG:4269",
        "transform_rule_id": "cr_nm_wellhistory_datum_1",
        **overrides,
    }
    with db.cursor() as cursor:
        cursor.execute(
            "insert into canonical.well_spatial (api10, geom_type, geom_key, geom, source_datum,"
            " transform_rule_id, source_manifest_id, derivation_id)"
            " values (%(api10)s, %(geom_type)s, %(geom_key)s,"
            " st_setsrid(st_geomfromtext(%(wkt)s), 4326), %(source_datum)s,"
            " %(transform_rule_id)s, %(manifest)s, %(derivation)s)",
            {**values, "manifest": manifest, "derivation": derivation},
        )


def test_canonical_wells_accepts_a_prefix_30_row(db, anchors) -> None:
    """No widening was needed. This guard exists so that stays true."""
    insert_well(db, anchors)

    with db.cursor() as cursor:
        cursor.execute("select state_code from canonical.wells where api10 = %s", (NM_API10,))
        assert cursor.fetchone() == ("30",)


def test_well_spatial_accepts_a_new_mexico_surface_point_with_its_transform_rule(db, anchors):
    insert_spatial(db, anchors)

    with db.cursor() as cursor:
        cursor.execute(
            "select geom_type, source_datum, transform_rule_id, st_srid(geom)"
            " from canonical.well_spatial where api10 = %s",
            (NM_API10,),
        )
        assert cursor.fetchone() == ("surface", "EPSG:4269", "cr_nm_wellhistory_datum_1", 4326)


@pytest.mark.parametrize("reason_code", ["coordinate_absent", "coordinate_sentinel"])
def test_the_two_coordinate_refusals_are_admitted_reason_codes(db, anchors, reason_code) -> None:
    manifest, _ = anchors
    with db.cursor() as cursor:
        cursor.execute(
            "insert into lineage.quarantine_rows (quarantine_id, row_fingerprint, source_id,"
            " staging_table, stage, reason_code, rule_id, row_payload, first_seen_at,"
            " first_seen_manifest_id, last_seen_at, last_seen_manifest_id, occurrence_count,"
            " state) values (%s, %s, 'nm_ocd_wellhistory',"
            " 'staging.stg_nm_ocd_wellhistory__records', 'validate', %s,"
            " 'cr_nm_wellhistory_coordinate_1', %s, now(), %s, now(), %s, 1, 'open')",
            (
                f"qr_{reason_code}",
                reason_code * 2,
                reason_code,
                Jsonb({"api10": NM_API10, "latitude": None}),
                manifest,
                manifest,
            ),
        )
        cursor.execute(
            "select count(*) from lineage.quarantine_rows where reason_code = %s", (reason_code,)
        )
        assert cursor.fetchone() == (1,)


def test_a_reason_code_outside_the_vocabulary_is_still_refused(db, anchors) -> None:
    """The two codes joined a vocabulary; they did not replace it with anything permissive."""
    manifest, _ = anchors
    with db.cursor() as cursor, pytest.raises(psycopg.errors.CheckViolation):
        cursor.execute(
            "insert into lineage.quarantine_rows (quarantine_id, row_fingerprint, source_id,"
            " staging_table, stage, reason_code, rule_id, row_payload, first_seen_at,"
            " first_seen_manifest_id, last_seen_at, last_seen_manifest_id, occurrence_count,"
            " state) values ('qr_bad', %s, 'nm_ocd_wellhistory',"
            " 'staging.stg_nm_ocd_wellhistory__records', 'validate', 'coordinate_wrongish',"
            " 'cr_nm_wellhistory_coordinate_1', %s, now(), %s, now(), %s, 1, 'open')",
            ("f" * 64, Jsonb({}), manifest, manifest),
        )


def test_the_sb01_handback_codes_are_not_landed_here(db) -> None:
    """crosswalk_disagreement and withheld_trade_secret belong to another track's amendment."""
    with db.cursor() as cursor:
        cursor.execute(
            "select pg_get_constraintdef(oid) from pg_constraint"
            " where conname = 'quarantine_rows_reason_code_check'"
        )
        definition = cursor.fetchone()[0]

    assert "coordinate_absent" in definition
    assert "coordinate_sentinel" in definition
    assert "crosswalk_disagreement" not in definition
    assert "withheld_trade_secret" not in definition


def test_the_append_only_triggers_fire_on_update_and_on_delete(db, anchors) -> None:
    insert_well(db, anchors)
    insert_spatial(db, anchors)
    db.commit()

    statements = (
        "update canonical.wells set well_name = 'X' where api10 = %s",
        "delete from canonical.wells where api10 = %s",
        "update canonical.well_spatial set source_datum = 'X' where api10 = %s",
        "delete from canonical.well_spatial where api10 = %s",
    )
    for statement in statements:
        with db.cursor() as cursor, pytest.raises(psycopg.errors.RestrictViolation):
            cursor.execute(statement, (NM_API10,))
        db.rollback()


def test_the_per_state_effective_scan_the_tile_marts_run_has_an_index(db) -> None:
    with db.cursor() as cursor:
        cursor.execute(
            "select indexdef from pg_indexes where schemaname = 'canonical'"
            "   and tablename = 'wells' and indexname = 'wells_state_effective_idx'"
        )
        row = cursor.fetchone()

    assert row is not None
    assert "state_code" in row[0]
    assert "effective_from DESC" in row[0]
