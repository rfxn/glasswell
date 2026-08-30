"""Deterministic ND physical-neighbour mart refresh and persisted integrity."""

from __future__ import annotations

from datetime import UTC, date, datetime

import psycopg
import pytest

from glasswell.lineage.capture import derive, lineage_session
from glasswell.lineage.models import OutputSpec
from glasswell.lineage.store import PostgresRecorder
from glasswell.marts.neighbors import MAX_RADIUS_M, refresh_neighbors, utm_zone_epsg
from glasswell.seed import seed_all
from tests.support.fakes import FixedClock
from tests.support.seed import seed_manifest, seed_well, seed_well_spatial

SUBJECT = "3305301001"
NEIGHBOR = "3305301002"
SECOND_NEIGHBOR = "3305301003"
UNMAPPED = "3305301004"
PARTIAL_ALIAS = "3305301005"
RUN_AT = datetime(2026, 8, 27, 6, tzinfo=UTC)


def _derivation(connection: psycopg.Connection, lineage_env) -> str:
    with lineage_session(
        recorder=PostgresRecorder(connection),
        environment=lineage_env,
        clock=FixedClock(RUN_AT),
        correlation_id="run_neighbor_inputs",
    ), derive(
        "canonical.promote",
        output=OutputSpec(
            store="postgres",
            dataset="canonical.production_monthly",
            partition={"source_id": "nd_mpr_xlsx", "vintage": "2026-08-27"},
        ),
        params={"fixture": "nd_neighbors"},
    ) as context:
        context.set_output_hash("9" * 64)
    return context.derivation_id


@pytest.fixture
def neighbor_inputs(db: psycopg.Connection, lineage_env) -> psycopg.Connection:
    seed_all(db)
    mpr_manifest = seed_manifest(db, sha256="7" * 64)
    fracfocus_manifest = seed_manifest(
        db,
        sha256="8" * 64,
        source_id="fracfocus_csv",
        source_key="fracfocus.csv",
    )
    derivation_id = _derivation(db, lineage_env)
    wells = (SUBJECT, NEIGHBOR, SECOND_NEIGHBOR, UNMAPPED, PARTIAL_ALIAS)
    for api10 in wells:
        seed_well(db, api10=api10, manifest_id=mpr_manifest, derivation_id=derivation_id)

    subject_wkt = "LINESTRING(-103.58 47.90, -103.54 47.90)"
    seed_well_spatial(
        db,
        api10=SUBJECT,
        geom_key="subject:b",
        wkt=subject_wkt,
        manifest_id=mpr_manifest,
        derivation_id=derivation_id,
    )
    seed_well_spatial(
        db,
        api10=SUBJECT,
        geom_key="subject:a",
        wkt=subject_wkt,
        manifest_id=mpr_manifest,
        derivation_id=derivation_id,
    )
    for api10, longitude, latitude in (
        (NEIGHBOR, -103.58, 47.91),
        (SECOND_NEIGHBOR, -103.58, 47.92),
        (UNMAPPED, -101.50, 47.90),
        (PARTIAL_ALIAS, -100.50, 47.90),
    ):
        seed_well_spatial(
            db,
            api10=api10,
            geom_key=f"{api10}:lateral",
            wkt=f"LINESTRING({longitude} {latitude}, {longitude + 0.04} {latitude})",
            manifest_id=mpr_manifest,
            derivation_id=derivation_id,
        )

    with db.cursor() as cursor:
        cursor.executemany(
            "insert into canonical.well_completion_anchors"
            " (disclosure_id, api10, completion_date, anchor_kind, source_id, report_vintage,"
            " source_manifest_id, derivation_id) values"
            " (%s, %s, %s, 'hydraulic_frac_job_end', 'fracfocus_csv', '2026-08-27', %s, %s)",
            [
                (f"ff-{api10}", api10, completion_date, fracfocus_manifest, derivation_id)
                for api10, completion_date in (
                    (SUBJECT, date(2025, 12, 20)),
                    (NEIGHBOR, date(2025, 10, 10)),
                    (SECOND_NEIGHBOR, date(2025, 12, 20)),
                    (UNMAPPED, date(2025, 9, 10)),
                    (PARTIAL_ALIAS, date(2025, 8, 10)),
                )
            ],
        )
        cursor.execute(
            "insert into lineage.formation_aliases"
            " (formation_raw, formation, formation_group, confidence, effective_from, source_id,"
            " created_vintage) values"
            " ('UNUSED SAME-DAY ALIAS', 'unused', '__other__', 0.800, '2026-08-27',"
            " 'nd_mpr_xlsx', '2026-08-27')"
        )
        cursor.executemany(
            "insert into canonical.well_completions"
            " (completion_key, api10, well_completion_pool, pool_reported, source_id,"
            " production_month, report_vintage, source_manifest_id, derivation_id) values"
            " (%s, %s, %s, %s, 'nd_mpr_xlsx', '2025-01-01', '2026-08-27', %s, %s)",
            [
                (f"{api10}:{pool}", api10, pool.lower().replace(" ", "_"), pool,
                 mpr_manifest, derivation_id)
                for api10, pool in (
                    (SUBJECT, "BAKKEN"),
                    (NEIGHBOR, "BAKKEN"),
                    (SECOND_NEIGHBOR, "THREE FORKS"),
                    (UNMAPPED, "UNREVIEWED POOL"),
                    (PARTIAL_ALIAS, "BAKKEN"),
                    (PARTIAL_ALIAS, "UNREVIEWED POOL"),
                )
            ],
        )
    db.commit()
    return db


def _refresh(connection: psycopg.Connection, lineage_env):
    with lineage_session(
        recorder=PostgresRecorder(connection),
        environment=lineage_env,
        clock=FixedClock(RUN_AT),
        correlation_id="run_neighbors",
    ):
        report = refresh_neighbors(connection)
    connection.commit()
    return report


def _resident_transaction_identity(connection: psycopg.Connection) -> tuple[list, ...]:
    queries = (
        "select to_jsonb(subject) from marts.nd_neighbor_subjects subject order by api10",
        "select to_jsonb(edge) from marts.nd_neighbor_edges edge"
        " order by api10, neighbor_api10",
        "select to_jsonb(derivation) from lineage.derivations derivation"
        " where output_dataset = 'marts.nd_neighbors' order by derivation_id",
        "select to_jsonb(input) from lineage.derivation_inputs input"
        " join lineage.derivations derivation using (derivation_id)"
        " where derivation.output_dataset = 'marts.nd_neighbors'"
        " order by input.derivation_id, input.ord",
        "select to_jsonb(rule_ref) from lineage.derivation_rules rule_ref"
        " join lineage.derivations derivation using (derivation_id)"
        " where derivation.output_dataset = 'marts.nd_neighbors'"
        " order by rule_ref.derivation_id, rule_ref.rule_id",
        "select to_jsonb(event) from lineage.audit_events event"
        " where event_type = 'mart.refreshed'"
        " and payload ->> 'dataset' = 'marts.nd_neighbors'"
        " order by occurred_at, event_id",
    )
    with connection.cursor() as cursor:
        identities = []
        for query in queries:
            cursor.execute(query)
            identities.append([row[0] for row in cursor.fetchall()])
    return tuple(identities)


def test_refresh_uses_every_component_classifies_partial_aliases_and_is_symmetric(
    neighbor_inputs: psycopg.Connection, lineage_env
) -> None:
    report = _refresh(neighbor_inputs, lineage_env)

    with neighbor_inputs.cursor() as cursor:
        cursor.execute(
            "select formation_status from marts.nd_neighbor_subjects where api10 = %s",
            (UNMAPPED,),
        )
        assert cursor.fetchone()[0] == "alias_unavailable"
        cursor.execute(
            "select formation_status from marts.nd_neighbor_subjects where api10 = %s",
            (PARTIAL_ALIAS,),
        )
        assert cursor.fetchone()[0] == "alias_unavailable"
        cursor.execute(
            "select api10, neighbor_api10, subject_geom_key, neighbor_geom_key, distance_m"
            " from marts.nd_neighbor_edges where api10 in (%s, %s)"
            " and neighbor_api10 in (%s, %s) order by api10",
            (SUBJECT, NEIGHBOR, SUBJECT, NEIGHBOR),
        )
        forward, reverse = cursor.fetchall()

    assert report.changed is True
    assert forward[:2] == (SUBJECT, NEIGHBOR)
    assert reverse[:2] == (NEIGHBOR, SUBJECT)
    assert forward[2:4] == ("subject:a", f"{NEIGHBOR}:lateral")
    assert reverse[2:4] == (f"{NEIGHBOR}:lateral", "subject:a")
    assert forward[4] == reverse[4]


def test_refresh_replays_exactly_and_repairs_a_mutated_resident_edge(
    neighbor_inputs: psycopg.Connection, lineage_env
) -> None:
    first = _refresh(neighbor_inputs, lineage_env)
    second = _refresh(neighbor_inputs, lineage_env)
    assert second.derivation_id == first.derivation_id
    assert second.changed is False

    with neighbor_inputs.cursor() as cursor:
        cursor.execute(
            "update marts.nd_neighbor_edges set distance_m = distance_m + 1"
            " where api10 = %s and neighbor_api10 = %s",
            (SUBJECT, NEIGHBOR),
        )
    neighbor_inputs.commit()

    repaired = _refresh(neighbor_inputs, lineage_env)
    assert repaired.derivation_id == first.derivation_id
    assert repaired.changed is True
    assert _refresh(neighbor_inputs, lineage_env).changed is False


def test_reverse_subject_foreign_key_has_a_supporting_index(db: psycopg.Connection) -> None:
    with db.cursor() as cursor:
        cursor.execute(
            "select index.indisvalid, index.indisready, index.indnkeyatts,"
            " pg_get_indexdef(index.indexrelid, 1, false),"
            " pg_get_indexdef(index.indexrelid, 2, false),"
            " pg_get_indexdef(index.indexrelid, 3, false)"
            " from pg_index index"
            " join pg_class relation on relation.oid = index.indexrelid"
            " join pg_namespace namespace on namespace.oid = relation.relnamespace"
            " where namespace.nspname = 'marts'"
            " and relation.relname = 'nd_neighbor_edges_reverse_fk_idx'"
        )
        index_state = cursor.fetchone()

    assert index_state == (
        True,
        True,
        3,
        "neighbor_api10",
        "snapshot_vintage",
        "derivation_id",
    )


def test_failed_replacement_rolls_back_the_resident_mart(
    neighbor_inputs: psycopg.Connection, lineage_env
) -> None:
    _refresh(neighbor_inputs, lineage_env)

    with neighbor_inputs.cursor() as cursor:
        cursor.execute(
            "insert into lineage.formation_aliases"
            " (formation_raw, formation, formation_group, confidence, effective_from, source_id,"
            " created_vintage) values"
            " ('UNREVIEWED POOL', 'reviewed_later', '__other__', 0.800, '2026-08-27',"
            " 'nd_mpr_xlsx', '2026-08-27')"
        )
        cursor.execute(
            "create function public.gw_test_reject_neighbor_subject() returns trigger"
            " language plpgsql as $$ begin raise exception 'injected subject failure'; end $$"
        )
        cursor.execute(
            "create trigger gw_test_reject_neighbor_subject before insert"
            " on marts.nd_neighbor_subjects for each row"
            " execute function public.gw_test_reject_neighbor_subject()"
        )
    neighbor_inputs.commit()
    transaction_before = _resident_transaction_identity(neighbor_inputs)
    neighbor_inputs.commit()

    with lineage_session(
        recorder=PostgresRecorder(neighbor_inputs),
        environment=lineage_env,
        clock=FixedClock(RUN_AT),
        correlation_id="run_neighbors_failed_replace",
    ), pytest.raises(psycopg.errors.RaiseException, match="injected subject failure"):
        refresh_neighbors(neighbor_inputs)
    neighbor_inputs.rollback()

    assert _resident_transaction_identity(neighbor_inputs) == transaction_before


def test_same_day_alias_append_changes_the_derivation_identity(
    neighbor_inputs: psycopg.Connection, lineage_env
) -> None:
    first = _refresh(neighbor_inputs, lineage_env)
    with neighbor_inputs.cursor() as cursor:
        cursor.execute(
            "insert into lineage.formation_aliases"
            " (formation_raw, formation, formation_group, confidence, effective_from, source_id,"
            " created_vintage) values"
            " ('UNREVIEWED POOL', 'reviewed_later', '__other__', 0.800, '2026-08-27',"
            " 'nd_mpr_xlsx', '2026-08-27')"
        )
    neighbor_inputs.commit()

    second = _refresh(neighbor_inputs, lineage_env)
    with neighbor_inputs.cursor() as cursor:
        cursor.execute(
            "select formation_status from marts.nd_neighbor_subjects where api10 = %s",
            (UNMAPPED,),
        )
        status = cursor.fetchone()[0]

    assert second.derivation_id != first.derivation_id
    assert second.changed is True
    assert status == "mapped"


def test_refresh_refuses_geometry_outside_the_measured_candidate_domain(
    neighbor_inputs: psycopg.Connection, lineage_env
) -> None:
    with neighbor_inputs.cursor() as cursor:
        cursor.execute(
            "select source_manifest_id, derivation_id from canonical.well_spatial"
            " where api10 = %s and geom_type = 'lateral' limit 1",
            (UNMAPPED,),
        )
        manifest_id, derivation_id = cursor.fetchone()
    seed_well_spatial(
        neighbor_inputs,
        api10=UNMAPPED,
        geom_key="outside-domain:lateral",
        # Re-anchored when the domain widened for Montana, never deleted: -105.50 is inside
        # the supported rectangle now, and this is the only proof the guard fires at all.
        # -118.00 is west of Montana, so it is outside the measured domain as -105.50 was.
        wkt="LINESTRING(-118.00 47.90, -117.96 47.90)",
        manifest_id=manifest_id,
        derivation_id=derivation_id,
    )
    neighbor_inputs.commit()

    with lineage_session(
        recorder=PostgresRecorder(neighbor_inputs),
        environment=lineage_env,
        clock=FixedClock(RUN_AT),
        correlation_id="run_neighbors_outside_domain",
    ), pytest.raises(RuntimeError, match="outside the measured candidate-CRS domain"):
        refresh_neighbors(neighbor_inputs)
    neighbor_inputs.rollback()

    with neighbor_inputs.cursor() as cursor:
        cursor.execute("select count(*) from marts.nd_neighbor_subjects")
        assert cursor.fetchone()[0] == 0


def test_refresh_refuses_an_existing_transaction(
    neighbor_inputs: psycopg.Connection, lineage_env
) -> None:
    with neighbor_inputs.cursor() as cursor:
        cursor.execute("select 1")

    with lineage_session(
        recorder=PostgresRecorder(neighbor_inputs), environment=lineage_env
    ), pytest.raises(RuntimeError, match="idle connection"):
        refresh_neighbors(neighbor_inputs)
    neighbor_inputs.rollback()


ND_BORDER = "3302599001"
MT_BORDER = "2508399001"
# The ND/MT line is the 27th meridian west of Washington, about -104.0489. These two laterals
# straddle it roughly 1.9 miles apart, well inside the 26,400 ft mart radius.
ND_BORDER_WKT = "LINESTRING(-104.02 48.00, -103.99 48.00)"
MT_BORDER_WKT = "LINESTRING(-104.08 48.00, -104.05 48.00)"


@pytest.fixture
def border_inputs(db: psycopg.Connection, lineage_env) -> psycopg.Connection:
    """One ND lateral and one Montana lateral, straddling the state line inside the radius."""
    seed_all(db)
    manifest = seed_manifest(db, sha256="a" * 64)
    derivation_id = _derivation(db, lineage_env)
    for api10, wkt in ((ND_BORDER, ND_BORDER_WKT), (MT_BORDER, MT_BORDER_WKT)):
        seed_well(db, api10=api10, manifest_id=manifest, derivation_id=derivation_id)
        seed_well_spatial(
            db,
            api10=api10,
            geom_key=f"{api10}:lateral",
            wkt=wkt,
            manifest_id=manifest,
            derivation_id=derivation_id,
        )
    db.commit()
    return db


def test_a_montana_well_enters_the_neighbour_set_of_the_nd_well_across_the_line(
    border_inputs: psycopg.Connection, lineage_env
) -> None:
    """The repair. Under '^33[0-9]{8}$' the Montana side could not be a subject or an edge."""
    _refresh(border_inputs, lineage_env)

    with border_inputs.cursor() as cursor:
        cursor.execute("select api10 from marts.nd_neighbor_subjects order by api10")
        assert [row[0] for row in cursor.fetchall()] == [MT_BORDER, ND_BORDER]

        cursor.execute(
            "select api10, neighbor_api10 from marts.nd_neighbor_edges order by api10"
        )
        assert cursor.fetchall() == [(MT_BORDER, ND_BORDER), (ND_BORDER, MT_BORDER)]


def test_the_cross_border_edge_is_measured_in_one_pair_local_zone(
    border_inputs: psycopg.Connection, lineage_env
) -> None:
    _refresh(border_inputs, lineage_env)

    with border_inputs.cursor() as cursor:
        cursor.execute(
            "select distinct distance_epsg from marts.nd_neighbor_edges"
        )
        assert [row[0] for row in cursor.fetchall()] == [utm_zone_epsg(-104.05)]
        cursor.execute("select distinct distance_m from marts.nd_neighbor_edges")
        distances = [float(row[0]) for row in cursor.fetchall()]
    # Both directions carry one measured distance, and it is inside the 26,400 ft mart radius.
    assert len(distances) == 1
    assert 0 < distances[0] <= float(MAX_RADIUS_M)


def test_the_sql_zone_expression_and_the_python_helper_agree(
    border_inputs: psycopg.Connection,
) -> None:
    """Two copies of the zone rule, pinned to each other rather than trusted separately."""
    longitudes = [-116.10 + step * 0.37 for step in range(54)]
    with border_inputs.cursor() as cursor:
        cursor.execute(
            "select longitude, 32600 + floor((longitude + 180) / 6)::int + 1"
            "  from unnest(%s::double precision[]) as longitude",
            (longitudes,),
        )
        rows = cursor.fetchall()

    assert rows, "the sweep produced no rows"
    assert [(longitude, utm_zone_epsg(longitude)) for longitude, _ in rows] == rows


def test_the_refresh_declares_every_state_it_scoped_to(
    border_inputs: psycopg.Connection, lineage_env
) -> None:
    """A multi-state mart that still declared one state would be lying in its own ledger."""
    _refresh(border_inputs, lineage_env)

    with border_inputs.cursor() as cursor:
        cursor.execute(
            "select params -> 'state_codes' from lineage.derivations"
            " where output_dataset = 'marts.nd_neighbors' and status = 'ok'"
            " order by created_at desc limit 1"
        )
        assert sorted(cursor.fetchone()[0]) == ["25", "33"]
