"""A5-F6 / A3-F3: the horizontals layer ships three segment kinds, and the ledger says so.

`unknown_vocab` claimed the ingest did not understand its own source for 24,872 rows whose
`segment` the ingest itself had parsed and written into the payload. The vocabulary is a rule
now, the label is the one that rule names, and a well whose horizontal trace was not promoted
says so on its card instead of reading as a well with no laterals.
"""

from __future__ import annotations

import psycopg
import pytest
from psycopg.types.json import Jsonb

from glasswell.seed import seed_all
from tests.integration.test_lateral_length_truth import laterals_loaded  # noqa: F401
from tests.integration.test_marts_nd import rows, scalar
from tests.integration.test_migration_014 import migration_sql
from tests.support.seed import seed_manifest

SEGMENT_RULE = "cr_nd_segment_vocab_1"
GIS_SOURCE = "nd_gis_horizontals_line"


def ledger(connection: psycopg.Connection) -> list[tuple]:
    return rows(
        connection,
        "select reason_code, rule_id, count(*), count(*) filter (where rule_id is null)"
        "  from lineage.quarantine_rows where source_id = %s group by 1, 2 order by 3 desc",
        (GIS_SOURCE,),
    )


def test_a_segment_the_layer_declares_is_not_unknown_vocabulary(laterals_loaded):  # noqa: F811
    labels = {reason for reason, _, _, _ in ledger(laterals_loaded)}

    assert "segment_not_promoted" in labels
    assert "unknown_vocab" not in labels


def test_the_not_promoted_rows_cite_the_rule_that_decided_them(laterals_loaded):  # noqa: F811
    """C17/U12: every quarantine row links to the conformance rule that rejected it."""
    labelled = rows(
        laterals_loaded,
        "select distinct rule_id, row_payload ->> 'segment'"
        "  from lineage.quarantine_rows"
        " where source_id = %s and reason_code = 'segment_not_promoted' order by 2",
        (GIS_SOURCE,),
    )

    assert labelled == [(SEGMENT_RULE, "STK"), (SEGMENT_RULE, "VERT")]


def test_only_the_lateral_segment_reaches_canonical(laterals_loaded):  # noqa: F811
    segments = {
        key.rsplit("_", 1)[-1][:3]
        for (key,) in rows(
            laterals_loaded,
            "select geom_key from canonical.well_spatial where geom_type = 'lateral'",
        )
    }

    assert segments == {"LAT"}


def test_the_card_discloses_a_horizontal_trace_that_was_not_promoted(
    laterals_loaded,  # noqa: F811
    api_client,
):
    """A3-F3: 68 production wells serve lateral_length_ft null while their sidetrack is held."""
    api10 = scalar(
        laterals_loaded,
        "select row_payload ->> 'api10' from lineage.quarantine_rows"
        " where source_id = %s and row_payload ->> 'segment' = 'STK' limit 1",
        (GIS_SOURCE,),
    )

    warnings = api_client.get(f"/v1/wells/{api10}").json()["meta"]["warnings"]

    disclosed = [w for w in warnings if w["code"] == "geometry_not_promoted"]
    assert disclosed, f"{api10} has a quarantined sidetrack and the card is silent"
    assert SEGMENT_RULE in disclosed[0]["detail"]
    assert disclosed[0]["pointer"] == "/geometry"


def test_a_well_whose_geometry_all_promoted_says_nothing(laterals_loaded, api_client):  # noqa: F811
    api10 = scalar(
        laterals_loaded,
        "select s.api10 from canonical.well_spatial s"
        " where s.geom_type = 'lateral' and not exists ("
        "     select 1 from lineage.quarantine_rows q where q.source_id = %s"
        "       and q.row_payload ->> 'api10' = s.api10) limit 1",
        (GIS_SOURCE,),
    )

    warnings = api_client.get(f"/v1/wells/{api10}").json()["meta"]["warnings"]

    assert [w for w in warnings if w["code"] == "geometry_not_promoted"] == []


@pytest.mark.parametrize("segment", ["VERT", "STK"])
def test_the_seeded_map_carries_the_segments_the_layer_ships(laterals_loaded, segment):  # noqa: F811
    promoted = scalar(
        laterals_loaded,
        "select promoted from lineage.nd_segment_map where segment = %s",
        (segment,),
    )

    assert promoted is False


def test_the_migration_relabels_only_what_the_payload_proves(db: psycopg.Connection) -> None:
    """The VM's 24,872 rows, bounded by their own evidence — migration 011's pattern."""
    seed_all(db)
    manifest = seed_manifest(db, sha256="f" * 64, source_id=GIS_SOURCE, source_key="OGD.zip")
    payloads = [
        ("qtn_seg_vert", {"api10": "3310506490", "linekey": "33105064900000_VERT",
                          "segment": "VERT"}),
        ("qtn_seg_stk", {"api10": "3301301523", "linekey": "33013015230000_STK1",
                         "segment": "STK"}),
        ("qtn_seg_none", {"api10": "3301301524", "linekey": "33013015240000_LAT1"}),
    ]
    with db.cursor() as cursor:
        for quarantine_id, payload in payloads:
            cursor.execute(
                "insert into lineage.quarantine_rows (quarantine_id, row_fingerprint, source_id,"
                " staging_table, stage, reason_code, row_payload, first_seen_at,"
                " first_seen_manifest_id, last_seen_at, last_seen_manifest_id)"
                " values (%s, %s, %s, 'staging.nd_gis_laterals', 'conform', 'unknown_vocab',"
                " %s, now(), %s, now(), %s)",
                (quarantine_id, quarantine_id, GIS_SOURCE, Jsonb(payload), manifest, manifest),
            )
        cursor.execute(migration_sql("segment_vocabulary"))
        cursor.execute(
            "select quarantine_id, reason_code, rule_id from lineage.quarantine_rows"
            " order by quarantine_id"
        )
        relabelled = cursor.fetchall()
        cursor.execute(
            "select payload from lineage.audit_events"
            " where event_id = 'evt_migration_016_cr_nd_segment_vocab_1'"
        )
        event = cursor.fetchone()

    assert relabelled == [
        ("qtn_seg_none", "unknown_vocab", None),
        ("qtn_seg_stk", "segment_not_promoted", SEGMENT_RULE),
        ("qtn_seg_vert", "segment_not_promoted", SEGMENT_RULE),
    ]
    assert event is not None
    assert event[0]["rows"] == 2
    assert event[0]["finding"] == "fp-audit A5-F6"
